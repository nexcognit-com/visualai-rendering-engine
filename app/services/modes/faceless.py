"""Mode 5 — Faceless Channel Automation (spec 015 / Step 3 PR-A).

Topic-driven, generic-stock-footage flow. Constitution Principle IV's
permitted exception: this is the ONE mode where Layer 3 may call
Pexels / Pixabay directly via :mod:`app.services.material`.

Behavioural shape mirrors the pre-VisualAI MoneyPrinterTurbo pipeline.
"""

from __future__ import annotations

from app.models.schema import VideoAspect, VideoParams
from app.services import llm

from ._interface import VisualsStrategy

name: str = "faceless"
default_aspect_ratio: VideoAspect = VideoAspect.portrait


def generate_script(params: VideoParams) -> str:
    """Topic-driven script via the standard generic LLM prompt."""
    return llm.generate_script(
        video_subject=params.video_subject,
        language=params.video_language or "",
        paragraph_number=params.paragraph_number or 1,
    )


def generate_terms(params: VideoParams, video_script: str) -> list[str]:
    """Generic Pexels-friendly terms drawn from topic + script."""
    return llm.generate_terms(
        video_subject=params.video_subject,
        video_script=video_script,
        amount=5,
    )


def select_visuals_strategy(params: VideoParams) -> VisualsStrategy:
    """Mode 5 forces auto-stock; user has no Visuals selector in the wizard."""
    return "auto"
