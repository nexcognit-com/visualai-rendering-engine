"""VisualAI upload endpoints — per-render asset persistence.

This file is shared between spec 009 (logo overlays) and spec 010 (music
control). Both endpoints save uploads to ``storage/uploads/<uuid>.<ext>``
with server-generated UUID4 filenames so user-supplied paths can never
traverse outside the upload directory.

NOTE: This is intentionally separate from the existing
``POST /api/v1/musics`` upstream endpoint, which writes to
``resource/songs/`` (the bundled BGM library). Per-render uploads land
in ``storage/uploads/`` so they don't pollute the bundled set.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from loguru import logger

from app.controllers.v1.base import new_router
from app.middleware.jwt_auth import jwt_required
from app.utils import utils

router = new_router()

# Audio MIME → extension. Browsers send slightly different MIMEs for the
# same format (Chrome vs Firefox vs Safari) — accept the common variants.
_AUDIO_MIMES: dict[str, str] = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",  # non-standard but seen from Firefox
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}

# Image MIME → extension. Used by spec 006 image uploads (model + product
# stills) and reserved for spec 009 logo uploads.
_IMAGE_MIMES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}

_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB per spec 010 FR-003
_MAX_LOGO_BYTES = 5 * 1024 * 1024    # 5 MB per spec 009 FR-002
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per spec 006 FR-008


def _validate_upload(
    file: UploadFile,
    allowed_mimes: dict[str, str],
    max_bytes: int,
) -> tuple[bytes, str, str]:
    """Read + validate a multipart upload.

    Returns (file_bytes, validated_mime, file_extension).
    Raises HTTPException with the contract's typed error_code on any failure.
    """
    if not file or not getattr(file, "filename", None):
        raise HTTPException(
            status_code=400,
            detail={"detail": "No file uploaded.", "error_code": "empty_upload"},
        )

    file.file.seek(0)
    body = file.file.read()
    if not body:
        raise HTTPException(
            status_code=400,
            detail={"detail": "No file uploaded.", "error_code": "empty_upload"},
        )

    if len(body) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail={
                "detail": f"Upload must be under {max_mb} MB.",
                "error_code": "file_too_large",
            },
        )

    mime = (file.content_type or "").lower().strip()
    if mime not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": f"Unsupported format: {mime!r}",
                "error_code": "unsupported_format",
            },
        )

    return body, mime, allowed_mimes[mime]


def _probe_audio_duration(path: str) -> float | None:
    """Return audio duration in seconds, or None if probe fails.

    Tries ``ffprobe`` first (metadata-only, fast), falls back to MoviePy.
    """
    # Primary: ffprobe.
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        out = result.stdout.strip()
        if out:
            return float(out)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning(f"ffprobe failed for {path}: {exc}; falling back to MoviePy")

    # Fallback: MoviePy.
    try:
        from moviepy import AudioFileClip
    except ImportError:
        try:
            from moviepy.editor import AudioFileClip  # type: ignore
        except ImportError:
            return None

    try:
        clip = AudioFileClip(path)
        duration = float(clip.duration)
        clip.close()
        return duration
    except Exception as exc:
        logger.error(f"MoviePy AudioFileClip failed for {path}: {exc}")
        return None


@router.post(
    "/uploads/audio",
    summary="Upload a custom audio track for per-render BGM (spec 010)",
)
def upload_audio(
    request: Request,
    file: UploadFile = File(...),
    _: dict = Depends(jwt_required),
) -> dict[str, Any]:
    body, mime, ext = _validate_upload(file, _AUDIO_MIMES, _MAX_AUDIO_BYTES)

    upload_dir = utils.storage_dir("uploads", create=True)
    uid = str(uuid.uuid4())
    filename = f"{uid}{ext}"
    save_path = os.path.join(upload_dir, filename)

    # Persist before probing — ffprobe needs a real file path.
    try:
        with open(save_path, "wb") as f:
            f.write(body)
        os.chmod(save_path, 0o644)
    except OSError as exc:
        logger.error(f"failed to write upload {save_path}: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Couldn't save your track — please retry.",
                "error_code": "storage_write_failed",
            },
        )

    duration = _probe_audio_duration(save_path)
    if duration is None or duration <= 0:
        # Bad audio — clean up before responding so we don't leak orphans.
        try:
            os.remove(save_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=415,
            detail={
                "detail": "This file appears corrupt — please re-export and try again.",
                "error_code": "invalid_audio",
            },
        )

    logger.info(
        f"audio uploaded: {filename} ({len(body)} bytes, {mime}, {duration:.2f}s)"
    )

    # Path returned is filesystem-relative from project root, matching the
    # bundled-track convention (`resource/songs/...`) so the engine can
    # resolve either one through the same `bgm_file` field.
    rel_path = os.path.relpath(save_path, utils.root_dir())

    return {
        "path": rel_path,
        "size_bytes": len(body),
        "mime_type": mime,
        "duration_seconds": round(duration, 2),
    }


# ---------------------------------------------------------------------------
# Spec 006: image uploads (model + product stills for "Use my own assets" mode)
# ---------------------------------------------------------------------------

# Target longest side after downscale. We DO NOT 9:16 crop at upload time
# anymore (Clarifications 2026-05-03 follow-up): destructive center-cropping
# threw away ~70% of landscape screenshots. Aspect-preserved downscale + a
# render-time contain-fit-with-blurred-background composite gives full image
# visibility without black bars. The "cropped.jpg" filename is preserved for
# backward compatibility with existing sidecars; it's actually the
# "downscaled, EXIF-corrected" derivative now.
_TARGET_LONGEST_SIDE = 1920

# Bomb / degenerate-input guards (post-decode):
_MIN_DIMENSION_PX = 100
_MAX_TOTAL_PIXELS = 100_000_000   # 100 MP — Pillow default DecompressionBombWarning ≈ 89 MP
_LOW_RES_WARN_PX = 720            # FR-009 soft-warning threshold


def _validate_role(role: str | None) -> str:
    if role not in ("model", "product"):
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "role must be 'model' or 'product'.",
                "error_code": "unsupported_role",
            },
        )
    return role


def _process_image_bytes(body: bytes) -> tuple[bytes, dict[str, Any]]:
    """Decode + verify + EXIF-transpose + downscale. Returns (jpeg_bytes, meta).

    Aspect-preserved downscale to ``_TARGET_LONGEST_SIDE`` on the longest side
    when the source exceeds it. Smaller sources are kept at native resolution.
    NO 9:16 cropping — the renderer's contain-fit composite handles framing.

    meta contains: source_width_px, source_height_px, cropped_width_px,
    cropped_height_px, low_res (bool). The "cropped" naming in meta is kept
    for wire-shape backward compatibility — the values now reflect the
    downscaled (but uncropped) dimensions.
    """
    # Lazy imports — Pillow ships transitively with MoviePy; importing only
    # at request time keeps API startup fast for non-image traffic.
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover — Pillow is a hard dep
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Image processing unavailable.",
                "error_code": "pillow_missing",
            },
        ) from exc

    # Pass 1 — Pillow.verify() validates the file structure without decoding.
    try:
        with Image.open(BytesIO(body)) as img:
            img.verify()
    except Exception as exc:
        logger.info(f"image verify failed: {exc}")
        raise HTTPException(
            status_code=415,
            detail={
                "detail": "This image appears corrupt — please re-export and try again.",
                "error_code": "invalid_image",
            },
        )

    # Pass 2 — actually decode for the crop. .verify() leaves the file in an
    # unusable state, so re-open from a fresh BytesIO.
    try:
        img = Image.open(BytesIO(body))
        img = ImageOps.exif_transpose(img)
    except Exception as exc:
        logger.info(f"image decode failed: {exc}")
        raise HTTPException(
            status_code=415,
            detail={
                "detail": "This image appears corrupt — please re-export and try again.",
                "error_code": "invalid_image",
            },
        )

    width, height = img.size
    if width < _MIN_DIMENSION_PX or height < _MIN_DIMENSION_PX:
        raise HTTPException(
            status_code=415,
            detail={
                "detail": "Image must be at least 100×100 pixels.",
                "error_code": "degenerate_dimensions",
            },
        )
    if width * height > _MAX_TOTAL_PIXELS:
        raise HTTPException(
            status_code=415,
            detail={
                "detail": "Image is too large to process — please resize and retry.",
                "error_code": "degenerate_dimensions",
            },
        )

    # Flatten alpha onto a neutral fill (FR Edge Cases — transparent PNGs).
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (20, 20, 20))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Aspect-preserved downscale only — no cropping.
    longest = max(width, height)
    if longest > _TARGET_LONGEST_SIDE:
        scale = _TARGET_LONGEST_SIDE / longest
        new_size = (int(round(width * scale)), int(round(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    cw, ch = img.size

    out = BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True, exif=b"")
    out_bytes = out.getvalue()

    return out_bytes, {
        "source_width_px": width,
        "source_height_px": height,
        "cropped_width_px": cw,
        "cropped_height_px": ch,
        "low_res": longest < _LOW_RES_WARN_PX,
    }


@router.post(
    "/uploads/image",
    summary="Upload a model or product image for spec 006 'Use my own assets' mode",
)
def upload_image(
    request: Request,
    file: UploadFile = File(...),
    role: str | None = Form(None),
    _: dict = Depends(jwt_required),
) -> dict[str, Any]:
    role_validated = _validate_role(role)
    body, mime, ext = _validate_upload(file, _IMAGE_MIMES, _MAX_IMAGE_BYTES)

    # Process FIRST so we don't write garbage to disk.
    cropped_bytes, meta = _process_image_bytes(body)

    upload_dir = utils.storage_dir("uploads", create=True)
    uid = str(uuid.uuid4())
    original_name = f"{uid}{ext}"
    cropped_name = f"{uid}.cropped.jpg"
    original_path = os.path.join(upload_dir, original_name)
    cropped_path = os.path.join(upload_dir, cropped_name)

    try:
        with open(original_path, "wb") as f:
            f.write(body)
        os.chmod(original_path, 0o644)
        with open(cropped_path, "wb") as f:
            f.write(cropped_bytes)
        os.chmod(cropped_path, 0o644)
    except OSError as exc:
        # Atomic cleanup — neither file should remain on a partial write.
        for p in (original_path, cropped_path):
            try:
                os.remove(p)
            except OSError:
                pass
        logger.error(f"failed to write upload {original_path}: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Couldn't save your image — please retry.",
                "error_code": "storage_write_failed",
            },
        )

    content_hash = "sha256:" + hashlib.sha256(body).hexdigest()
    rel_original = os.path.relpath(original_path, utils.root_dir())
    rel_cropped = os.path.relpath(cropped_path, utils.root_dir())

    logger.info(
        f"image uploaded: role={role_validated} {cropped_name} "
        f"({len(body)} bytes, {mime}, {meta['source_width_px']}x{meta['source_height_px']}"
        f" → {meta['cropped_width_px']}x{meta['cropped_height_px']})"
    )

    response: dict[str, Any] = {
        "path": rel_cropped,
        "original_path": rel_original,
        "size_bytes": len(body),
        "mime_type": mime,
        "source_width_px": meta["source_width_px"],
        "source_height_px": meta["source_height_px"],
        "cropped_width_px": meta["cropped_width_px"],
        "cropped_height_px": meta["cropped_height_px"],
        "content_hash": content_hash,
    }
    if meta["low_res"]:
        response["warning"] = "low_resolution"
    return response


# ---------------------------------------------------------------------------
# Spec 018 — Mode 4 UGC Avatar Generator: selfie upload + list-recent
# ---------------------------------------------------------------------------
#
# Hybrid last-3 retention model (FR-014, Q2=C resolution): each tenant has
# three numbered slots. Uploads land in the lowest-numbered free slot OR
# evict the oldest occupied slot (mtime-based) when all three are taken.
# No DB schema; each upload writes a sidecar `<uuid>.meta.json` for
# downstream traceability.

_SELFIE_VIDEO_MIMES: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",  # rare but accepted
}

_MAX_SELFIE_BYTES = 100 * 1024 * 1024  # 100 MB per spec 018 contracts/selfie-upload.md
_SELFIE_MIN_DURATION_S = 5.0
_SELFIE_MAX_DURATION_S = 60.0  # FR-001 — accept up to 60s, only first 15s used as ref
_SELFIE_MIN_SHORT_SIDE_PX = 480
_SELFIE_MIN_FPS = 24.0


def _probe_selfie_metadata(path_str: str) -> dict:
    """Run ffprobe for video duration, fps, dimensions."""
    out = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_frames:format=duration",
            "-of", "json",
            path_str,
        ],
        capture_output=True, text=True, check=True,
    )
    import json as _json
    data = _json.loads(out.stdout)
    streams = data.get("streams") or []
    if not streams:
        return {"duration_s": 0.0, "width": 0, "height": 0, "fps": 0.0}
    s = streams[0]
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or 0.0)
    fps_raw = s.get("r_frame_rate") or "0/1"
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den) if float(den) > 0 else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "duration_s": duration,
        "width": int(s.get("width") or 0),
        "height": int(s.get("height") or 0),
        "fps": fps,
    }


def _evict_oldest_avatar_if_full(tenant_id: str) -> int:
    """Pick a slot to write into — the lowest-numbered free slot, OR the
    oldest by mtime if all 3 are full (eviction).

    Eviction deletes both the .mp4 and the .meta.json sidecar.
    Returns the chosen slot number (1, 2, or 3).
    """
    parent = utils.tenant_avatar_dir(tenant_id, slot=None, create=True)
    candidates = []
    for n in (1, 2, 3):
        slot_dir = os.path.join(parent, f"slot{n}")
        if not os.path.isdir(slot_dir):
            return n  # First free slot wins
        files = [f for f in os.listdir(slot_dir) if f.endswith(".mp4")]
        if not files:
            return n  # Empty slot wins
        # Pick oldest mtime as eviction candidate
        oldest = min(files, key=lambda f: os.path.getmtime(os.path.join(slot_dir, f)))
        candidates.append((os.path.getmtime(os.path.join(slot_dir, oldest)), n, slot_dir, oldest))

    # All 3 occupied — evict the oldest by mtime
    candidates.sort()
    _, slot_n, slot_dir, oldest_file = candidates[0]
    oldest_path = os.path.join(slot_dir, oldest_file)
    meta_path = oldest_path[:-4] + ".meta.json"
    for p in (oldest_path, meta_path):
        try:
            os.remove(p)
        except OSError:
            pass
    logger.info(f"selfie eviction: tenant={tenant_id} slot={slot_n} removed {oldest_file}")
    return slot_n


@router.post(
    "/uploads/selfie",
    status_code=200,
    summary="Spec 018 — Upload a Mode-4 selfie speaker reference.",
)
def upload_selfie(
    request: Request,
    file: UploadFile = File(...),
    auth: Any = Depends(jwt_required),
):
    """Upload a 5-60s selfie video for use as the speaker reference in
    Mode 4 UGC Avatar renders. Validates format, duration, frame rate,
    resolution, AND face-detection BEFORE persisting.

    Hybrid last-3 retention: writes to one of three per-tenant slots,
    evicting the oldest by mtime when full.

    Returns the `Speaker Reference` shape per data-model.md Entity 1
    (uuid, slot, path, duration_seconds, face_bbox, face_count_detected,
    width, height, warnings).
    """
    tenant_id = (auth.get("tenant_id") if isinstance(auth, dict) else None) or "demo-tenant-001"
    user_id = (auth.get("user_id") if isinstance(auth, dict) else None) or "demo-user-001"

    raw_mime = (file.content_type or "").lower()
    # Browsers' MediaRecorder emits Content-Type with a codecs param
    # (e.g. "video/webm;codecs=vp8"). Strip parameters before lookup.
    mime = raw_mime.split(";", 1)[0].strip()
    ext = _SELFIE_VIDEO_MIMES.get(mime)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "format_unsupported", "message": f"Unsupported MIME: {raw_mime}"},
        )

    # Read body with cap
    body = file.file.read(_MAX_SELFIE_BYTES + 1)
    if len(body) > _MAX_SELFIE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "payload_too_large", "message": "Max 100 MB."},
        )
    if not body:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "format_unsupported", "message": "Empty upload."},
        )

    # Stage to a temp location for ffprobe + face detect BEFORE committing to slot.
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="selfie_upload_")
    try:
        tmp_path = os.path.join(tmp_dir, "in" + ext)
        with open(tmp_path, "wb") as f:
            f.write(body)

        meta = _probe_selfie_metadata(tmp_path)
        if meta["duration_s"] < _SELFIE_MIN_DURATION_S or meta["duration_s"] > _SELFIE_MAX_DURATION_S:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "duration_out_of_range",
                    "message": f"Duration {meta['duration_s']:.1f}s outside [5, 60]s.",
                    "details": {"duration_seconds": meta["duration_s"]},
                },
            )
        if meta["fps"] < _SELFIE_MIN_FPS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "frame_rate_too_low",
                    "message": f"Frame rate {meta['fps']:.1f} < {_SELFIE_MIN_FPS} fps.",
                },
            )
        short_side = min(meta["width"], meta["height"])
        if short_side < _SELFIE_MIN_SHORT_SIDE_PX:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "resolution_too_low",
                    "message": f"Shortest side {short_side}px < {_SELFIE_MIN_SHORT_SIDE_PX}px.",
                },
            )

        # Face detection — reject early per FR-002.
        from app.services import lip_sync
        try:
            face_bbox = lip_sync.detect_face(tmp_path)
        except ValueError:  # no_face_detected
            raise HTTPException(
                status_code=400,
                detail={"error_code": "no_face_detected", "message": "No face detected in the uploaded video."},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"selfie face-detect crashed: {exc!r}")
            raise HTTPException(
                status_code=500,
                detail={"error_code": "internal_validation_failed", "message": "Face detection error."},
            )

        # Pick slot + commit.
        slot = _evict_oldest_avatar_if_full(tenant_id)
        slot_dir = utils.tenant_avatar_dir(tenant_id, slot=slot, create=True)
        uid = uuid.uuid4().hex[:12]
        # Always write as .mp4 — remux non-mp4 sources.
        target_path = os.path.join(slot_dir, f"{uid}.mp4")
        if ext == ".mp4":
            shutil.move(tmp_path, target_path)
        else:
            # WebM (VP8/VP9) and MKV cannot be stream-copied into an MP4
            # container, so re-encode the video to h264. Audio is dropped
            # since MuseTalk synthesises narration from the script.
            subprocess.run(
                [
                    shutil.which("ffmpeg") or "ffmpeg", "-loglevel", "error", "-y",
                    "-i", tmp_path,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                    target_path,
                ],
                check=True, capture_output=True, text=True,
            )

        warnings: list[str] = []
        if face_bbox.get("face_count", 1) > 1:
            warnings.append("multiple_faces_detected")
        if face_bbox.get("confidence", 0.0) < 0.85:
            warnings.append("face_partially_obscured")
        if meta["fps"] < 30 and meta["fps"] >= _SELFIE_MIN_FPS:
            warnings.append("low_frame_rate")

        rel_path = os.path.relpath(target_path, utils.root_dir())
        response: dict[str, Any] = {
            "uuid": uid,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "slot": slot,
            "path": rel_path,
            "duration_seconds": round(meta["duration_s"], 2),
            "width": meta["width"],
            "height": meta["height"],
            "face_count_detected": face_bbox.get("face_count", 1),
            "face_bbox": {
                "x": face_bbox["x"], "y": face_bbox["y"],
                "w": face_bbox["w"], "h": face_bbox["h"],
                "confidence": round(face_bbox["confidence"], 3),
            },
            "warnings": warnings,
        }
        # Sidecar metadata for the list-recent endpoint.
        import json as _json
        meta_path = target_path[:-4] + ".meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            _json.dump(response, f, indent=2)

        logger.info(
            f"selfie_upload tenant={tenant_id} user={user_id} slot={slot} "
            f"uuid={uid} duration={meta['duration_s']:.1f}s "
            f"faces={face_bbox.get('face_count', 1)}"
        )
        return response
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except OSError:
            pass


@router.get(
    "/uploads/selfie/recent",
    summary="Spec 018 — List a tenant's last-3 selfies.",
)
def list_recent_selfies(
    request: Request,
    auth: Any = Depends(jwt_required),
):
    """Return up to 3 most-recent speaker references for the calling
    tenant. Used by the L1 wizard's recent-selfies picker (FR-014).

    Empty list when no slots are occupied. Slots are scanned by mtime
    descending so the picker shows newest-first.
    """
    tenant_id = (auth.get("tenant_id") if isinstance(auth, dict) else None) or "demo-tenant-001"
    parent = utils.tenant_avatar_dir(tenant_id, slot=None, create=True)
    items: list[dict] = []
    for n in (1, 2, 3):
        slot_dir = os.path.join(parent, f"slot{n}")
        if not os.path.isdir(slot_dir):
            continue
        for fname in os.listdir(slot_dir):
            if not fname.endswith(".meta.json"):
                continue
            try:
                with open(os.path.join(slot_dir, fname), "r", encoding="utf-8") as f:
                    import json as _json
                    items.append(_json.load(f))
            except (OSError, ValueError):
                continue
    # Newest first by mtime of the .mp4
    def _mtime(item):
        p = os.path.join(utils.root_dir(), item.get("path", ""))
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0
    items.sort(key=_mtime, reverse=True)
    return {"items": items[:3]}
