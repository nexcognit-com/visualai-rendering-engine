"""Spec 015 / Step 3 — Mode 2 zero-regression check (T050).

The registry refactor (modes/__init__.py + short.py + faceless.py) and the
material.py rewrite must not change observable behaviour for Mode 2 callers.
This test exercises task.generate_script and task.generate_terms with a
Mode 2 params shape and asserts the LLM helper functions get called with
the same arguments they did pre-refactor.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schema import VideoParams
from app.services import task


def _mode_2_params() -> VideoParams:
    return VideoParams(
        video_subject="matte black water bottle",
        mode="short",
        paragraph_number=1,
        video_language="en",
    )


def test_us3_1_mode_2_auto_calls_llm_with_correct_args():
    params = _mode_2_params()
    params.video_script = ""  # auto path

    with patch("app.services.modes.short.llm.generate_script", return_value="ad copy") as gen_script:
        out = task.generate_script("tsk-1", params)

    assert out == "ad copy"
    gen_script.assert_called_once()
    kwargs = gen_script.call_args.kwargs
    assert kwargs["video_subject"] == "matte black water bottle"
    assert kwargs["language"] == "en"


def test_us3_2_mode_2_verbatim_skips_llm():
    """Verbatim path doesn't call the registry — script stays as-is."""
    params = _mode_2_params()
    params.video_script = "Hand-typed marketing copy."
    params.script_mode = "verbatim"

    with patch("app.services.modes.short.llm.generate_script") as gen_script:
        out = task.generate_script("tsk-2", params)

    assert out == "Hand-typed marketing copy."
    gen_script.assert_not_called()


def test_us3_3_mode_2_terms_routes_to_short_module():
    params = _mode_2_params()

    with patch("app.services.modes.short.llm.generate_terms", return_value=["a", "b", "c"]) as gen_terms:
        out = task.generate_terms("tsk-3", params, "video script content")

    assert out == ["a", "b", "c"]
    gen_terms.assert_called_once()


def test_us3_4_unknown_mode_falls_back_gracefully(monkeypatch):
    """Unknown mode value falls back to llm.generate_script directly (forward-compat)."""
    params = _mode_2_params()
    params.video_script = ""
    # Simulate a future mode value that's not yet registered
    monkeypatch.setattr(params, "mode", "future_mode_xyz")

    with patch("app.services.task.llm.generate_script", return_value="fallback") as fallback:
        out = task.generate_script("tsk-4", params)

    assert out == "fallback"
    fallback.assert_called_once()


def test_us3_5_faceless_terms_routes_to_faceless_module():
    params = _mode_2_params()
    params.mode = "faceless"

    with patch("app.services.modes.faceless.llm.generate_terms", return_value=["x", "y"]) as gen_terms:
        out = task.generate_terms("tsk-5", params, "topic-driven script")

    assert out == ["x", "y"]
    gen_terms.assert_called_once()
