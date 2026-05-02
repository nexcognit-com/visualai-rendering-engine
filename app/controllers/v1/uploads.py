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

from fastapi import File, Form, HTTPException, Request, UploadFile
from loguru import logger

from app.controllers.v1.base import new_router
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
def upload_audio(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
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
