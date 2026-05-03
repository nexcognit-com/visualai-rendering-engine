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
    """Topic-driven script with **research-then-write** grounding.

    Spec 015 Mode-5 quality: pull 3-5 short factual snippets from a web
    search before generation so the LLM doesn't have to rely on its
    training-time knowledge alone (especially for time-sensitive topics
    like "the science of waking up at 5am" where studies cited may be
    outdated). DDGS lookup is best-effort: on failure, falls back to
    ungrounded generation so the wizard always returns a video.
    """
    topic = (params.video_subject or "").strip()
    facts = llm.research_topic(topic) if topic else []
    return llm.generate_faceless_script_grounded(
        topic=topic,
        facts=facts,
        duration_seconds=60,
        language=params.video_language or "en",
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
