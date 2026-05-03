"""Spec 015 — Mode 5 (faceless) module (T018)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schema import VideoAspect, VideoParams
from app.services.modes import faceless


@pytest.fixture
def params() -> VideoParams:
    return VideoParams(
        video_subject="the science of waking up early",
        mode="faceless",
        paragraph_number=1,
        video_language="en",
    )


def test_face1_generate_script_returns_string(params: VideoParams) -> None:
    """generate_script orchestrates research_topic + generate_faceless_script_grounded.
    Mock both to keep the test deterministic + free-of-network."""
    with patch("app.services.modes.faceless.llm.research_topic", return_value=[]), \
         patch("app.services.modes.faceless.llm.generate_faceless_script_grounded",
               return_value="topic-script-stub"):
        out = faceless.generate_script(params)
    assert out == "topic-script-stub"


def test_face2_generate_terms_returns_list(params: VideoParams) -> None:
    with patch(
        "app.services.modes.faceless.llm.generate_terms",
        return_value=["sunrise", "morning routine", "alarm clock", "stretching", "coffee"],
    ):
        out = faceless.generate_terms(params, "some script text")
    assert isinstance(out, list)
    assert len(out) == 5


def test_face3_select_visuals_strategy_always_auto(params: VideoParams) -> None:
    """Mode 5 forces auto regardless of params.visuals_mode."""
    assert faceless.select_visuals_strategy(params) == "auto"
    # Even if a Mode-5 caller somehow set visuals_mode (via direct API hit),
    # the mode's selector ignores it.
    params.visuals_mode = "user_uploaded"
    assert faceless.select_visuals_strategy(params) == "auto"
    params.visuals_mode = "hybrid"
    assert faceless.select_visuals_strategy(params) == "auto"


def test_face4_default_aspect_ratio_portrait() -> None:
    assert faceless.default_aspect_ratio == VideoAspect.portrait


def test_face_module_name_attribute() -> None:
    assert faceless.name == "faceless"
