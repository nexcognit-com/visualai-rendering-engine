"""Mode 2 — Short Marketing Video (spec 015 / Step 3 PR-A).

The registry's first concrete entry. Wraps existing ``app.services.llm``
helpers so Mode 2 byte-for-byte preserves pre-Step-3 behaviour. Adding
mode-specific prompt variations (e.g. wiring ``llm.generate_marketing_script``
into the auto path) is a future enhancement that lands as a separate
behavioural-change PR — Step 3 keeps the refactor structurally pure.
"""

from __future__ import annotations

from typing import Literal

from app.models.schema import VideoAspect, VideoParams
from app.services import llm
from app.services.voice import infer_language_from_voice

from ._interface import VisualsStrategy

name: str = "short"
default_aspect_ratio: VideoAspect = VideoAspect.portrait


def generate_script(params: VideoParams) -> str:
    """Mode 2 script generation.

    Currently delegates to :func:`llm.generate_script` for byte-for-byte
    behavioural preservation. Future enhancement: switch to
    :func:`llm.generate_marketing_script` when the wizard signals
    marketing-style intent.
    """
    # When the wizard doesn't pass an explicit language (the L1 dropdown
    # currently always sends ""), derive it from the chosen voice's locale.
    # Otherwise an Arabic voice (e.g. ar-EG-SalmaNeural) ends up reading
    # an English script — Edge TTS reads whatever text you give it, so the
    # result is unintelligible. 2026-05-05 regression caught after the
    # voice-catalog dropdown expansion to multilingual voices.
    language = params.video_language or infer_language_from_voice(params.voice_name)
    return llm.generate_script(
        video_subject=params.video_subject,
        language=language,
        paragraph_number=params.paragraph_number or 1,
    )


def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Mode 2 term generation. Hybrid path uses setting-tag two-pass
    (already in ``llm.generate_setting_terms``); auto path uses the
    standard product-centric terms via :func:`llm.generate_terms`.

    The hybrid two-pass is kept INSIDE the route handler today
    (``controllers/v1/video.py``) which writes it into the sidecar before
    dispatch — so calling this function for hybrid would double up. The
    function still returns generic terms as a sane default; callers in
    the hybrid wizard path bypass it via the sidecar.
    """
    return llm.generate_terms(
        video_subject=params.video_subject,
        video_script=video_script,
        amount=5,
    )


def select_visuals_strategy(params: VideoParams) -> VisualsStrategy:
    """Pass through user's wizard choice. Defaults to "auto" if unset."""
    chosen = params.visuals_mode or "auto"
    if chosen not in ("auto", "user_uploaded", "hybrid"):
        return "auto"
    return chosen  # type: ignore[return-value]
