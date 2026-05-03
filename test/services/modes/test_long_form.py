"""Spec 016 — Mode 3 long-form registry entry contract test."""

from __future__ import annotations

from unittest.mock import patch

from app.models.schema import VideoAspect, VideoParams
from app.services import modes
from app.services.modes import long_form


def test_lf1_default_aspect_is_landscape() -> None:
    assert long_form.default_aspect_ratio == VideoAspect.landscape


def test_lf2_target_resolution_is_1080p() -> None:
    assert long_form.target_resolution == (1920, 1080)


def test_lf3_duration_choices_are_2_to_5_minutes() -> None:
    assert long_form.duration_choices_seconds == (120, 180, 240, 300)


def test_lf4_default_duration_is_3_minutes() -> None:
    assert long_form.default_duration_seconds == 180


def test_lf5_subtitle_band_in_lower_third() -> None:
    """FR-006 / SC-003 — subtitles MUST land between 75% and 90% of frame height."""
    assert 0.75 <= long_form.subtitle_band_y_pct <= 0.90


def test_lf6_segment_count_range_8_to_25() -> None:
    lo, hi = long_form.segment_count_range
    assert lo == 8 and hi == 25


def test_lf7_registry_includes_long_mode() -> None:
    assert "long" in modes.supported()
    m = modes.pick("long")
    assert m.name == "long"


def test_lf8_generate_long_form_script_returns_structured_dict() -> None:
    """T010 mirror — verify the helper returns the four-key dict shape."""
    fake_response = (
        '{"hook": "Hook line.", "body": ["Point A.", "Point B.", "Point C."], '
        '"summary": "Summary line."}'
    )
    with patch("app.services.llm._generate_response", return_value=fake_response):
        from app.services import llm
        out = llm.generate_long_form_script(
            input_text="test topic", source_type="topic", target_duration_seconds=180
        )
    assert set(out.keys()) == {"hook", "body", "summary", "full_text"}
    assert out["hook"] == "Hook line."
    assert out["body"] == ["Point A.", "Point B.", "Point C."]
    assert out["summary"] == "Summary line."
    assert "Hook line." in out["full_text"]
    assert "Summary line." in out["full_text"]


def test_lf9_generate_long_form_script_handles_empty_llm() -> None:
    """All-retries-failed path returns empty dict (not exception)."""
    with patch("app.services.llm._generate_response", return_value=""):
        from app.services import llm
        out = llm.generate_long_form_script("topic", "topic", 180)
    assert out == {"hook": "", "body": [], "summary": "", "full_text": ""}


def test_lf10_mode_registry_fallback_script_uses_long_form_helper() -> None:
    """Layer 3 fallback path: when video_script is empty, generate_script
    calls llm.generate_long_form_script with a sane duration."""
    fake_response = (
        '{"hook": "Hook.", "body": ["A.", "B.", "C."], "summary": "Sum."}'
    )
    params = VideoParams(
        video_subject="why X matters",
        mode="long",
        video_clip_duration=20,
        video_count=9,  # 20 * 9 = 180 — falls inside choices
    )
    with patch("app.services.llm._generate_response", return_value=fake_response):
        out = long_form.generate_script(params)
    assert "Hook." in out and "Sum." in out
