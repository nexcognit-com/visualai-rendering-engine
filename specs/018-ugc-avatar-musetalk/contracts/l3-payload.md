# Contract — L3 Mode 4 Payload + Pipeline

**Surface**: L3's existing `POST /api/v1/videos` accepts an extended `VideoParams` for `mode="ugc_avatar"`. The schema lives in `app/models/schema.py`; the rendering pipeline dispatches via `app/services/modes/ugc_avatar.py` (registry entry per Constitution Principle V).

## VideoParams extension

The existing Pydantic model in `app/models/schema.py` gains:

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | `Literal["faceless", "short", "long", "ugc_avatar"]` | `"faceless"` | New value `"ugc_avatar"` added to the literal. |
| `speaker_reference_path` | `Optional[str]` | `None` | Required when `mode == "ugc_avatar"`. Absolute path or pre-signed URL. Validated at controller-dispatch time. |

No other VideoParams changes. All existing fields (voice_name, video_subject, video_script, script_mode, video_language, etc.) carry through.

## Mode registry entry

New file `app/services/modes/ugc_avatar.py` declares Mode 4's behavioral contract:

```python
"""Mode 4 — UGC Avatar Generator (spec 018)."""
from __future__ import annotations
from typing import Final
from app.models.schema import VideoAspect, VideoParams
from app.services import llm
from app.services.voice import infer_language_from_voice
from ._interface import VisualsStrategy

name: str = "ugc_avatar"
default_aspect_ratio: VideoAspect = VideoAspect.portrait

# Mode 4 has no fixed duration band — accepts 15..300s like Mode 3.
duration_min_seconds: Final[int] = 15
duration_max_seconds: Final[int] = 300
default_duration_seconds: Final[int] = 30

# 9:16 portrait, lower-third subtitle band (matches Mode 2).
target_resolution: Final[tuple[int, int]] = (1080, 1920)
subtitle_band_y_pct: Final[float] = 0.80
subtitle_band_color: Final[str] = "#000000"
subtitle_band_opacity: Final[float] = 0.60

# No per-segment B-roll — face IS the visual. Explicitly null.
segment_count_range: Final[tuple[int, int] | None] = None

# Same Hook→Body→CTA template as Mode 2.
script_template: Final[str] = "HOOK_BODY_CTA"


def generate_script(params: VideoParams) -> str:
    """Mode 4 fallback (when L2 didn't run the orchestrator).

    Produces the same Hook→Body→CTA marketing script as Mode 2 — Mode 4
    is just Mode 2 with the user's face instead of Pexels stock.
    """
    language = (
        params.video_language
        or infer_language_from_voice(params.voice_name)
        or "en"
    )
    return llm.generate_marketing_script(
        product_info=params.video_subject or "",
        duration_seconds=params.video_clip_duration * params.video_count,
        language=language,
    )


def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Mode 4 has no stock-footage terms (face is the visual). Returns []."""
    return []


def select_visuals_strategy(params: VideoParams) -> VisualsStrategy:
    """Mode 4 always uses the user-uploaded selfie as its visual source.

    Returns "user_uploaded" so existing visuals-mode plumbing routes
    correctly. The path is in params.speaker_reference_path.
    """
    return "user_uploaded"
```

## Pipeline — `task.py` dispatch path

`app/services/task.py`'s render task picks up `mode="ugc_avatar"` and runs:

1. **Validate** — `speaker_reference_path` resolves to a readable file. If not → fail with `speaker_reference_not_found`.
2. **Script generation** — already done by L2 (verbatim) OR fallback to `mode_impl.generate_script(params)` (Auto/Polish).
3. **TTS** — existing `app/services/voice.py` synth path. Output: `storage/tasks/<task_id>/audio.mp3`.
4. **Loop extension** — call `app/services/lip_sync.py::extend_reference_to_duration(speaker_reference_path, audio_duration)` if audio_duration > reference_duration. Output: `storage/tasks/<task_id>/extended_reference.mp4`. Otherwise skip.
5. **Lip-sync inference** — call `lip_sync.run(reference_path, audio_path, output_path)`. Output: `storage/tasks/<task_id>/lipsync.mp4`.
6. **Subtitles** — existing `app/services/subtitle.py` generates `.srt` from audio. Existing `app/services/video.py::generate_video` burns them in (with the Arabic font auto-swap that already ships).
7. **Finalize** — output to `storage/tasks/<task_id>/final-1.mp4`.

The pipeline reuses every existing service except the new `lip_sync.py`. No new orchestrator in L3 — `task.py`'s existing flow handles it via the mode registry.

## `app/services/lip_sync.py` — public surface

```python
"""Lip-sync inference wrapper (spec 018, R1=MuseTalk self-hosted)."""
from __future__ import annotations
from pathlib import Path

# Engine selector — defaults to musetalk; "mock" returns the input unchanged
# (used in CI smoke and on hosts without GPU/MPS).
LIP_SYNC_ENGINE: str  # env var read at module import


def detect_face(video_path: Path) -> dict:
    """MediaPipe face detection. Returns the face_bbox dict per data-model.md."""
    ...


def extend_reference_to_duration(
    ref_path: Path,
    target_seconds: float,
    *,
    output_path: Path,
) -> Path:
    """Ping-pong loop the reference video to match target_seconds."""
    ...


def run(
    reference_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    face_bbox: dict | None = None,
) -> Path:
    """Run the chosen lip-sync engine. Output: 9:16 MP4 with mouth synced."""
    ...
```

## Failure modes

| Trigger | error_code | http (when surfaced via L2) |
|---|---|---|
| `mode="ugc_avatar"` but no `speaker_reference_path` | `speaker_reference_required` | 400 |
| Reference file missing on disk | `speaker_reference_not_found` | 400 |
| MuseTalk model load failure (corrupted weights, OOM at startup) | `lip_sync_engine_unavailable` | 503 |
| Inference OOM during a render | `lip_sync_oom` | 503 |
| Audio duration > 300s (validation slip-through) | `audio_duration_exceeds_cap` | 400 |
| FFmpeg failure during loop extension | `loop_extension_failed` | 500 |
| Script generation (fallback) returned empty | existing `script_generation_failed` | 500 |

## Configuration

New env vars introduced for L3:

| Var | Default | Description |
|---|---|---|
| `LIP_SYNC_ENGINE` | `"musetalk"` | One of `"musetalk"`, `"mock"`. Mock returns the input video unchanged (dev/CI). |
| `MUSETALK_MODEL_DIR` | `"~/.cache/musetalk"` | Where weights are downloaded/loaded from. |
| `MUSETALK_DEVICE` | (auto-detect) | One of `"cuda"`, `"mps"`, `"cpu"`. Module picks CUDA → MPS → CPU automatically when unset. |
| `LIP_SYNC_LOOP_SEAM_FADE_SECONDS` | `0.0` | Optional crossfade duration at ping-pong seams. 0 = pure pivot (research.md R5 recommends pure pivot). |
