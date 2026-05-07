"""Mode 3 — Long-Form Video (16:9 YouTube, 2-5 min) — spec 016.

Constitution Principle V: this module is the single source of truth for
Mode 3's aspect ratio, duration choices, subtitle position, and script
structure. Layer 2 builds the script + B-roll list upstream and dispatches
here with ``mode="long"``; Layer 3 stitches narration + visuals + subtitles.

Unlike Mode 2 (``short``) which delegates script-gen to ``llm.generate_script``,
Mode 3's script is normally produced upstream in Layer 2 (calling
:func:`llm.generate_long_form_script`). This module's ``generate_script`` is
the fallback path when a Mode 3 task arrives at Layer 3 with an empty
``video_script`` field — it grounds on ``video_subject`` like Mode 2 does.
"""

from __future__ import annotations

from typing import Final

from app.models.schema import VideoAspect, VideoParams
from app.services import llm
from app.services.voice import infer_language_from_voice

from ._interface import VisualsStrategy

name: str = "long"
default_aspect_ratio: VideoAspect = VideoAspect.landscape

# Public configuration consumed by Layer 2 + the controller. Keep these in
# sync with `specs/016-long-form-video/contracts/layer3-render-contract.md`.
target_resolution: Final[tuple[int, int]] = (1920, 1080)
# Duration choices extended 2026-05-08 to cover YouTube long-form (8 + 10 min).
# Trade-off: 10-min renders take ~50-70 min wall-clock on M-series silicon
# (visual_relevance + ffmpeg stitch + Edge TTS scale linearly with duration).
# Twelve Labs cost stays under the $1 budget at 10 min (~$0.50-0.65 per render).
duration_choices_seconds: Final[tuple[int, ...]] = (120, 180, 240, 300, 480, 600)
default_duration_seconds: Final[int] = 180
word_budget_per_minute: Final[int] = 150
subtitle_band_y_pct: Final[float] = 0.80
subtitle_text_color: Final[str] = "#FFFFFF"
subtitle_band_color: Final[str] = "#000000"
subtitle_band_opacity: Final[float] = 0.60
# Segment count range widened to support 10-min videos (~30-40 segments at
# the 12-15s/shot pacing the long_form_script prompt targets).
segment_count_range: Final[tuple[int, int]] = (8, 40)
music_volume_db: Final[int] = -18
script_template: Final[str] = "HOOK_BODY_SUMMARY"


def generate_script(params: VideoParams) -> str:
    """Mode 3 fallback script generation.

    Layer 2 normally produces the long-form script via
    :func:`llm.generate_long_form_script` BEFORE dispatching to Layer 3.
    This function only runs if the dispatched task has no script — it
    extracts a duration target from ``video_clip_duration * video_count``
    (fallback 180s) and routes to the long-form helper.
    """
    target_seconds = default_duration_seconds
    if params.video_clip_duration and params.video_count:
        # Caller usually fills these to define segments; product = total seconds.
        target_seconds = int(params.video_clip_duration) * int(params.video_count)
        # Clamp to valid range.
        if target_seconds < duration_choices_seconds[0]:
            target_seconds = duration_choices_seconds[0]
        elif target_seconds > duration_choices_seconds[-1]:
            target_seconds = duration_choices_seconds[-1]
    language = (
        params.video_language
        or infer_language_from_voice(params.voice_name)
        or "en"
    )
    result = llm.generate_long_form_script(
        input_text=params.video_subject or "",
        source_type="topic",
        target_duration_seconds=target_seconds,
        language=language,
    )
    return result.get("full_text", "")


def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Mode 3 term generation. Reuses Mode 2's product-centric path; the
    longer script gives the LLM more material to extract distinctive terms
    from. Layer 2.5 handles the actual B-roll fetch using these terms.
    """
    return llm.generate_terms(
        video_subject=params.video_subject,
        video_script=video_script,
        amount=8,  # ≈ matches segment_count_range lower bound
    )


def select_visuals_strategy(params: VideoParams) -> VisualsStrategy:
    """Pass through user's wizard choice; default "auto" (Layer 2.5 routes
    to AI-gen for URL-source tasks and Pixabay stock for topic-source tasks).
    """
    chosen = params.visuals_mode or "auto"
    if chosen not in ("auto", "user_uploaded", "hybrid"):
        return "auto"
    return chosen  # type: ignore[return-value]
