"""Lip-sync inference wrapper (spec 018 — Mode 4 UGC Avatar Generator).

Public surface (per [contracts/l3-payload.md](specs/018-ugc-avatar-musetalk/contracts/l3-payload.md)):
- :func:`detect_face` — MediaPipe-backed face detection on a video.
- :func:`extend_reference_to_duration` — ping-pong loop (FR-015) to match audio length.
- :func:`run` — engine-selectable lip-sync inference (`musetalk` | `mock`).

Engine selection via env var ``LIP_SYNC_ENGINE`` (default: ``mock``).
- ``musetalk`` — real PyTorch inference. Requires the vendored MuseTalk
  install via ``scripts/install_musetalk.sh``. Auto-picks CUDA → MPS → CPU.
- ``mock`` — copies the speaker reference verbatim to the output path
  (no inference). Used in CI, on hosts without GPU/MPS, and during L1/L2
  iteration that doesn't need to validate lip-sync quality.

Constitutional notes (spec 018 plan.md § Complexity Tracking):
- This module is a NEW file outside the 6 named fork-surfaces in
  Constitution Principle II. Justified: lip-sync is a distinct concern
  (parallel to ``app/services/voice.py`` for TTS), warrants a focused
  module that can be tested + replaced independently of MoviePy/FFmpeg.
- Self-hosted MuseTalk is local PyTorch — NOT an external generation API
  (Constitution Principle IV is NOT triggered, see research.md R1).
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from loguru import logger


# ---------------------------------------------------------------------------
# Module-level config (read from env once at import time)
# ---------------------------------------------------------------------------

# "musetalk" or "mock". Default is "mock" so dev hosts without GPU/MPS
# don't break on import — the wrapper just copies the reference unchanged.
LIP_SYNC_ENGINE: Final[str] = os.environ.get("LIP_SYNC_ENGINE", "mock").strip().lower()

# Where MuseTalk weights live. Only consulted when LIP_SYNC_ENGINE=musetalk.
MUSETALK_MODEL_DIR: Final[str] = os.path.expanduser(
    os.environ.get("MUSETALK_MODEL_DIR", "~/.cache/musetalk")
)

# Optional override for the inference device. Empty/unset = auto-detect.
_MUSETALK_DEVICE_OVERRIDE: Final[str] = os.environ.get("MUSETALK_DEVICE", "").strip().lower()

# Optional crossfade duration at ping-pong loop seams (FR-015). 0.0 = pure
# pivot per research.md R5. Bump if a particular reference shows visible jumps.
LIP_SYNC_LOOP_SEAM_FADE_SECONDS: Final[float] = float(
    os.environ.get("LIP_SYNC_LOOP_SEAM_FADE_SECONDS", "0.0") or "0.0"
)


# ---------------------------------------------------------------------------
# T010 — Device auto-detection (cuda → mps → cpu)
# ---------------------------------------------------------------------------

def _pick_device() -> str:
    """Return the best inference backend on this host.

    Honour ``MUSETALK_DEVICE`` env override first; otherwise auto-detect.
    Returns one of ``"cuda"``, ``"mps"``, ``"cpu"``. Logs the chosen
    backend on first call.
    """
    if _MUSETALK_DEVICE_OVERRIDE in ("cuda", "mps", "cpu"):
        logger.info(f"lip_sync._pick_device: env override → {_MUSETALK_DEVICE_OVERRIDE}")
        return _MUSETALK_DEVICE_OVERRIDE

    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("lip_sync._pick_device: torch not installed; defaulting to cpu")
        return "cpu"

    if torch.cuda.is_available():
        logger.info("lip_sync._pick_device: torch.cuda available → cuda")
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        logger.info("lip_sync._pick_device: torch.backends.mps available → mps (Apple Silicon)")
        return "mps"
    logger.info("lip_sync._pick_device: no GPU/MPS → cpu (slow)")
    return "cpu"


# ---------------------------------------------------------------------------
# T008 — MediaPipe face detection
# ---------------------------------------------------------------------------

# Tunable: how many evenly-spaced frames we sample from the source. Lower =
# faster but may miss the largest face; higher = more accurate but slower.
_FACE_DETECT_FRAME_SAMPLES: Final[int] = 30

# Reject uploads where every sampled frame's max-confidence < this threshold.
_FACE_DETECT_MIN_CONFIDENCE: Final[float] = 0.7


_FACE_MODEL_URL: Final[str] = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
_FACE_MODEL_PATH: Final[str] = os.path.expanduser(
    "~/.cache/mediapipe/blaze_face_short_range.tflite"
)
_face_detector_cache = None


def _ensure_face_model() -> str:
    """Download the BlazeFace tflite model on first use; cache locally."""
    if os.path.isfile(_FACE_MODEL_PATH):
        return _FACE_MODEL_PATH
    os.makedirs(os.path.dirname(_FACE_MODEL_PATH), exist_ok=True)
    import urllib.request
    logger.info(f"lip_sync._ensure_face_model: downloading {_FACE_MODEL_URL}")
    urllib.request.urlretrieve(_FACE_MODEL_URL, _FACE_MODEL_PATH)
    return _FACE_MODEL_PATH


def _get_face_detector():
    """Return a cached MediaPipe Tasks FaceDetector instance."""
    global _face_detector_cache
    if _face_detector_cache is not None:
        return _face_detector_cache
    from mediapipe.tasks import python as mp_tasks  # type: ignore[import-not-found]
    from mediapipe.tasks.python import vision  # type: ignore[import-not-found]
    options = vision.FaceDetectorOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=_ensure_face_model()),
        min_detection_confidence=_FACE_DETECT_MIN_CONFIDENCE,
        running_mode=vision.RunningMode.IMAGE,
    )
    _face_detector_cache = vision.FaceDetector.create_from_options(options)
    return _face_detector_cache


def detect_face(video_path: Path | str) -> dict:
    """Detect the dominant face in a video clip.

    Samples ``_FACE_DETECT_FRAME_SAMPLES`` frames evenly across the clip,
    runs MediaPipe Tasks FaceDetector (BlazeFace short-range) on each,
    picks the largest centred face with confidence >= ``_FACE_DETECT_MIN_CONFIDENCE``.

    Returns:
        ``{"x", "y", "w", "h", "confidence", "frames_scanned",
           "max_confidence", "face_count", "source_width", "source_height"}``

    Raises:
        ValueError: when no face exceeds confidence threshold across any
            sampled frame. Caller should map this to ``no_face_detected``.
        FileNotFoundError: when ``video_path`` doesn't resolve.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(str(video_path))

    try:
        import cv2  # type: ignore[import-not-found]
        import mediapipe as mp  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(f"lip_sync.detect_face: missing dep — {exc}") from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"lip_sync.detect_face: cv2 cannot open {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise RuntimeError(f"lip_sync.detect_face: zero frames in {video_path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    sample_indices = sorted(set(
        int(i * total_frames / _FACE_DETECT_FRAME_SAMPLES)
        for i in range(_FACE_DETECT_FRAME_SAMPLES)
    ))

    detector = _get_face_detector()
    best_face: tuple[int, int, int, int] | None = None
    best_conf = 0.0
    best_score = 0.0
    max_face_count = 0

    for idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)
        if not result.detections:
            continue
        max_face_count = max(max_face_count, len(result.detections))
        for det in result.detections:
            bbox = det.bounding_box
            x = max(0, int(bbox.origin_x))
            y = max(0, int(bbox.origin_y))
            w = max(0, int(bbox.width))
            h = max(0, int(bbox.height))
            if w <= 0 or h <= 0:
                continue
            area = w * h
            cx = x + w / 2
            cy = y + h / 2
            center_dist = math.hypot(cx - width / 2, cy - height / 2)
            center_factor = max(0.1, 1.0 - center_dist / max(width, height))
            conf = det.categories[0].score if det.categories else 0.0
            score = area * center_factor * conf
            if score > best_score:
                best_score = score
                best_face = (x, y, w, h)
                best_conf = conf

    cap.release()

    if best_face is None:
        raise ValueError("no_face_detected")

    x, y, w, h = best_face
    return {
        "x": x, "y": y, "w": w, "h": h,
        "confidence": best_conf,
        "frames_scanned": len(sample_indices),
        "max_confidence": best_conf,
        "face_count": max_face_count,
        "source_width": width,
        "source_height": height,
    }


# ---------------------------------------------------------------------------
# T009 — Ping-pong loop extension (FR-015)
# ---------------------------------------------------------------------------

_FFMPEG_BIN: Final[str] = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE_BIN: Final[str] = shutil.which("ffprobe") or "ffprobe"


def _probe_duration_seconds(path: Path) -> float:
    """Run ffprobe for a file's duration in seconds."""
    out = subprocess.run(
        [
            _FFPROBE_BIN, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extend_reference_to_duration(
    ref_path: Path | str,
    target_seconds: float,
    *,
    output_path: Path | str,
) -> Path:
    """Ping-pong loop the reference video to ≥ target_seconds, then trim exact.

    Strategy: build forward+reverse twice (or as many times as needed),
    concatenate, then ``-t target_seconds`` trim. Per research.md R5,
    ping-pong gives a clean motion-pivot at every loop seam — no visible
    jump cut, no blur (vs crossfade).

    No-op when ``ref_duration >= target_seconds`` (just copy the file).

    Args:
        ref_path: source speaker reference video.
        target_seconds: desired output duration (typically equals the audio length).
        output_path: where to write the extended MP4.

    Returns:
        The output path as a ``Path``.

    Raises:
        RuntimeError: ffmpeg failed.
        FileNotFoundError: ref_path missing.
    """
    ref_path = Path(ref_path)
    output_path = Path(output_path)
    if not ref_path.is_file():
        raise FileNotFoundError(str(ref_path))

    ref_duration = _probe_duration_seconds(ref_path)
    if ref_duration <= 0:
        raise RuntimeError(f"lip_sync.extend_reference: zero-duration ref {ref_path}")

    if ref_duration >= target_seconds:
        # No extension needed; just copy + trim.
        cmd = [
            _FFMPEG_BIN, "-loglevel", "error", "-y",
            "-i", str(ref_path),
            "-t", f"{target_seconds:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(
            f"lip_sync.extend_reference: ref={ref_duration:.1f}s ≥ target="
            f"{target_seconds:.1f}s; copied + trimmed"
        )
        return output_path

    # Build a ping-pong sequence long enough to cover target_seconds.
    # Each ping-pong cycle (forward + reverse) doubles the source length.
    cycles_needed = math.ceil(target_seconds / (ref_duration * 2))
    # Build a filtergraph: split input → reverse one copy → concat both.
    # Repeat the [forward][reverse] block `cycles_needed` times.
    filter_parts = []
    for _ in range(cycles_needed):
        filter_parts.append("[0:v]null[fwd]")  # placeholder, rewritten below
    # The actual ping-pong filter for one cycle:
    #   [0:v]reverse[rev];[0:v][rev]concat=n=2:v=1[pp]
    # For multiple cycles we just concat the [pp] block N times.
    # Implementation: build cycles_needed copies of the pp block then concat.
    fg_parts = []
    for i in range(cycles_needed):
        fg_parts.append(
            f"[0:v]reverse[rev{i}];"
            f"[0:v][rev{i}]concat=n=2:v=1[pp{i}]"
        )
    concat_inputs = "".join(f"[pp{i}]" for i in range(cycles_needed))
    fg_full = (
        ";".join(fg_parts)
        + f";{concat_inputs}concat=n={cycles_needed}:v=1[out]"
    )
    cmd = [
        _FFMPEG_BIN, "-loglevel", "error", "-y",
        "-i", str(ref_path),
        "-filter_complex", fg_full,
        "-map", "[out]",
        "-t", f"{target_seconds:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    logger.info(
        f"lip_sync.extend_reference: ref={ref_duration:.1f}s target="
        f"{target_seconds:.1f}s cycles={cycles_needed}"
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"lip_sync.extend_reference: ffmpeg exited {proc.returncode}: "
            f"{(proc.stderr or '')[:500]}"
        )
    out_duration = _probe_duration_seconds(output_path)
    logger.success(
        f"lip_sync.extend_reference: wrote {output_path.name} "
        f"duration={out_duration:.2f}s (target {target_seconds:.2f}s)"
    )
    return output_path


# ---------------------------------------------------------------------------
# T011 — Real MuseTalk inference path
# T012 — Mock engine path
# ---------------------------------------------------------------------------

# Lazy-loaded module-level singletons. Filled on first call to _musetalk_infer().
_musetalk_loaded = False


def _crop_face_region_to_9_16(
    reference_path: Path,
    face_bbox: dict,
    output_path: Path,
) -> Path:
    """F8 — pad/crop the source video to a 9:16 frame centered on the face.

    For any source aspect ratio (4:3, 16:9, 9:16), compute a 9:16-tight crop
    centered on the detected face. The crop region anchors at the face center
    and extends ±9:16 of the face HEIGHT, then we resize to 1080×1920.
    """
    src_w = face_bbox["source_width"]
    src_h = face_bbox["source_height"]
    fx, fy, fw, fh = face_bbox["x"], face_bbox["y"], face_bbox["w"], face_bbox["h"]
    face_cx = fx + fw / 2
    face_cy = fy + fh / 2

    # Target 9:16. Pick crop height so the face fills ~half the frame.
    target_face_height_pct = 0.45  # face occupies ~45% of crop height
    crop_h = max(int(fh / target_face_height_pct), 1)
    crop_w = max(int(crop_h * 9 / 16), 1)

    # Anchor crop on face center; clamp to source bounds.
    x0 = max(0, min(src_w - crop_w, int(face_cx - crop_w / 2)))
    y0 = max(0, min(src_h - crop_h, int(face_cy - crop_h / 2)))
    # Pad with edge replication if the face is too close to a frame edge.
    pad_x = max(0, crop_w - src_w) if crop_w > src_w else 0
    pad_y = max(0, crop_h - src_h) if crop_h > src_h else 0

    # FFmpeg crop+scale to 1080×1920. When crop > source, pad first.
    if pad_x > 0 or pad_y > 0:
        vf = (
            f"pad=w={crop_w}:h={crop_h}:x={pad_x // 2}:y={pad_y // 2}:color=black,"
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    else:
        vf = (
            f"crop=w={crop_w}:h={crop_h}:x={x0}:y={y0},"
            f"scale=1080:1920:flags=bicubic"
        )

    cmd = [
        _FFMPEG_BIN, "-loglevel", "error", "-y",
        "-i", str(reference_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"lip_sync._crop_face_region_to_9_16: ffmpeg exited {proc.returncode}: "
            f"{(proc.stderr or '')[:500]}"
        )
    return output_path


def _musetalk_infer(
    reference_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    face_bbox: dict | None,
) -> Path:
    """Real MuseTalk inference path. Loads the vendored MuseTalk module and
    runs the inference pipeline.

    On first call:
      - Adds vendor/musetalk/ to sys.path.
      - Imports MuseTalk's inference helpers.
      - Validates MUSETALK_MODEL_DIR points at downloaded weights.

    Subsequent calls reuse the loaded model.

    See research.md R1 for engine selection rationale.
    """
    global _musetalk_loaded
    device = _pick_device()

    if not _musetalk_loaded:
        # Vendor path is parent-of-app/services/lip_sync.py + /vendor/musetalk
        vendor_dir = Path(__file__).resolve().parents[2] / "vendor" / "musetalk"
        if not vendor_dir.is_dir():
            raise RuntimeError(
                "lip_sync._musetalk_infer: vendor/musetalk/ not found. "
                "Run scripts/install_musetalk.sh to clone + install."
            )
        if str(vendor_dir) not in sys.path:
            sys.path.insert(0, str(vendor_dir))

        if not Path(MUSETALK_MODEL_DIR).is_dir():
            raise RuntimeError(
                f"lip_sync._musetalk_infer: MUSETALK_MODEL_DIR={MUSETALK_MODEL_DIR} "
                "missing. Run scripts/install_musetalk.sh to download weights."
            )
        logger.info(
            f"lip_sync._musetalk_infer: loading MuseTalk from "
            f"{vendor_dir} on device={device} weights={MUSETALK_MODEL_DIR}"
        )
        # NOTE: actual MuseTalk loading is integration-specific. The vendored
        # repo's inference entry point lives under musetalk/scripts/inference.py
        # (or similar — exact API depends on the pinned SHA). T011 below
        # documents the integration; concrete implementation lands when an
        # operator runs scripts/install_musetalk.sh on a GPU host.
        _musetalk_loaded = True

    raise NotImplementedError(
        "lip_sync._musetalk_infer: real MuseTalk integration is a Phase-2.1 task. "
        "For now, set LIP_SYNC_ENGINE=mock to use the bypass path. "
        "Integration tracking: spec 018 tasks.md T011 (deferred until scripts/"
        "install_musetalk.sh has been validated against a real GPU host)."
    )


def _mock_infer(
    reference_path: Path,
    audio_path: Path,
    output_path: Path,
) -> Path:
    """Mock engine — copy the speaker reference verbatim to output_path.

    Used in CI, on hosts without GPU/MPS, and for L1/L2 iteration that
    doesn't need real lip-sync. The downstream video assembly still runs
    (subtitle burn-in, final encode), so end-to-end pipeline correctness
    is verifiable without paying the lip-sync wall time.
    """
    # Force re-encode to ensure the output is a clean MP4 (some references
    # are .mov/.webm; downstream assembly assumes .mp4).
    cmd = [
        _FFMPEG_BIN, "-loglevel", "error", "-y",
        "-i", str(reference_path),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"lip_sync._mock_infer: ffmpeg exited {proc.returncode}: "
            f"{(proc.stderr or '')[:500]}"
        )
    logger.info(
        f"lip_sync._mock_infer: copied reference → {output_path.name} "
        "(LIP_SYNC_ENGINE=mock — real lip-sync skipped)"
    )
    return output_path


def run(
    reference_path: Path | str,
    audio_path: Path | str,
    output_path: Path | str,
    *,
    face_bbox: dict | None = None,
) -> Path:
    """Run the configured lip-sync engine.

    Dispatches based on ``LIP_SYNC_ENGINE`` (read once at module import):
    - ``musetalk`` → :func:`_musetalk_infer` (real PyTorch inference).
    - ``mock`` → :func:`_mock_infer` (verbatim copy of reference).

    Args:
        reference_path: speaker reference video. Should already be the
            ping-pong-extended version when audio > selfie duration
            (caller is responsible for that step via :func:`extend_reference_to_duration`).
        audio_path: TTS audio MP3 to lip-sync to.
        output_path: where to write the lip-synced MP4.
        face_bbox: optional pre-detected face bbox from :func:`detect_face`.
            When provided, :func:`_crop_face_region_to_9_16` (F8) tightens
            the frame to a 9:16 crop centered on the face before inference.
            When None, the source frame is passed through unchanged
            (for already-9:16 references).

    Returns:
        The output path as a ``Path``.

    Raises:
        RuntimeError: engine-specific errors (model load, OOM, ffmpeg).
        NotImplementedError: when LIP_SYNC_ENGINE=musetalk but the vendored
            install hasn't been validated against a real GPU host yet.
    """
    reference_path = Path(reference_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = LIP_SYNC_ENGINE
    logger.info(
        f"lip_sync.run: engine={engine!r} ref={reference_path.name} "
        f"audio={audio_path.name} → {output_path.name}"
    )

    # F8 — Optional 9:16 crop centered on detected face. We do this regardless
    # of engine when face_bbox is provided so the mock path also produces
    # 9:16 output (matches Mode 4 spec FR-006).
    if face_bbox is not None:
        cropped = output_path.with_stem(output_path.stem + "_cropped")
        _crop_face_region_to_9_16(reference_path, face_bbox, cropped)
        reference_path = cropped

    if engine == "musetalk":
        return _musetalk_infer(reference_path, audio_path, output_path, face_bbox=face_bbox)
    if engine == "mock":
        return _mock_infer(reference_path, audio_path, output_path)
    raise RuntimeError(f"lip_sync.run: unknown LIP_SYNC_ENGINE={engine!r} (expected musetalk|mock)")
