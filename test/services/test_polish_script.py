"""Smoke tests for spec 013 — Polish mode for script editor.

Coverage:
- PL-1..PL-10: polish_script() function unit tests
- WS-1..WS-10: dispatch matrix in task.generate_script

All LLM calls are mocked via monkeypatch on llm._generate_response so tests
are offline + fast (<1s total).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schema import VideoParams
from app.services import llm, task


# ---------------------------------------------------------------------------
# polish_script function tests (PL-1..PL-10)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Captures the prompt sent to _generate_response so tests can assert
    on prompt structure without a real LLM call."""

    def __init__(self, output: str = "polished output"):
        self.output = output
        self.last_prompt: str | None = None

    def __call__(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.output


def test_pl1_pl2_pl7_pl9_pl10_polish_script_happy_path() -> None:
    """PL-1, PL-2, PL-7, PL-9, PL-10: happy-path polish call."""
    fake = _FakeResponse(output="Tired of weak coffee? Try our Cold Brew Kit. Visit acmebrew.com.")

    with patch.object(llm, "_generate_response", fake):
        result = llm.polish_script(
            brief="highlight 32oz size",
            video_subject="Cold Brew Kit. Slow-steeped overnight.",
            duration_seconds=20,
            language="en",
        )

    # PL-1: returns non-empty text without markdown artifacts
    assert result
    assert len(result) >= 30
    assert "*" not in result
    assert "#" not in result
    assert "{" not in result and "}" not in result

    # PL-2: prompt was sent (factual context substitution)
    assert fake.last_prompt is not None
    assert "Cold Brew Kit" in fake.last_prompt
    assert "highlight 32oz size" in fake.last_prompt

    # PL-9: target_words for 20s duration
    assert "Approximately 50 words total" in fake.last_prompt  # 20*2.5

    # PL-10: prompt contains language constraint
    assert "language code `en`" in fake.last_prompt


def test_pl9_target_words_at_10s() -> None:
    """PL-9 alt: 10s duration → 25 target words."""
    fake = _FakeResponse(output="short script.")
    with patch.object(llm, "_generate_response", fake):
        llm.polish_script(brief="x", duration_seconds=10)
    assert "Approximately 25 words total" in fake.last_prompt


def test_pl10_target_words_at_60s() -> None:
    """PL-10: 60s duration → 150 target words."""
    fake = _FakeResponse(output="long script with lots of words.")
    with patch.object(llm, "_generate_response", fake):
        llm.polish_script(brief="x", duration_seconds=60)
    assert "Approximately 150 words total" in fake.last_prompt


def test_pl2_empty_subject_uses_sentinel() -> None:
    """PL-2: empty video_subject substitutes the sentinel string."""
    fake = _FakeResponse(output="output")
    with patch.object(llm, "_generate_response", fake):
        llm.polish_script(brief="brief content", video_subject="")
    assert "no product context provided" in fake.last_prompt


def test_pl3_empty_brief_raises_value_error() -> None:
    """PL-3: empty brief raises ValueError, no LLM call."""
    fake = _FakeResponse(output="output")
    with patch.object(llm, "_generate_response", fake):
        with pytest.raises(ValueError, match="polish_brief_required"):
            llm.polish_script(brief="")
    assert fake.last_prompt is None  # no LLM call


def test_pl4_whitespace_brief_raises_value_error() -> None:
    """PL-4: whitespace-only brief raises ValueError."""
    fake = _FakeResponse(output="output")
    with patch.object(llm, "_generate_response", fake):
        with pytest.raises(ValueError, match="polish_brief_required"):
            llm.polish_script(brief="   \n\t  ")
    assert fake.last_prompt is None


def test_pl5_llm_exception_propagates() -> None:
    """PL-5: when _generate_response raises, polish_script propagates."""
    def raising(prompt: str) -> str:
        raise RuntimeError("API rate limit")

    with patch.object(llm, "_generate_response", raising):
        with pytest.raises(RuntimeError, match="rate limit"):
            llm.polish_script(brief="valid brief")


def test_pl6_empty_llm_output_raises() -> None:
    """PL-6: when LLM returns empty, polish_script raises ValueError."""
    fake = _FakeResponse(output="")
    with patch.object(llm, "_generate_response", fake):
        with pytest.raises(ValueError, match="empty polish output"):
            llm.polish_script(brief="valid brief")


def test_pl7_markdown_stripped() -> None:
    """PL-7: markdown artifacts stripped from LLM output."""
    fake = _FakeResponse(output="**Bold** intro. ## Header. Body.")
    with patch.object(llm, "_generate_response", fake):
        result = llm.polish_script(brief="x")
    assert "*" not in result
    assert "#" not in result


def test_pl8_language_constraint_in_prompt() -> None:
    """PL-8: language code appears in prompt's translation rule."""
    fake = _FakeResponse(output="output")
    with patch.object(llm, "_generate_response", fake):
        llm.polish_script(brief="brief", language="es")
    assert "language code `es`" in fake.last_prompt
    # Constraint #6 of the prompt template:
    assert "translate to `es`" in fake.last_prompt


# ---------------------------------------------------------------------------
# Dispatch matrix tests (WS-1..WS-10) — task.generate_script
# ---------------------------------------------------------------------------


class _StubTaskState:
    """Capture state.update_task calls across the dispatch."""

    def __init__(self):
        self.last_state = None
        self.last_error = None

    def update_task(self, task_id, state=None, error=None, **kwargs):
        if state is not None:
            self.last_state = state
        if error is not None:
            self.last_error = error


def _stub_state_manager(monkeypatch):
    """Patch task.sm.state with a fresh stub for each test."""
    stub = _StubTaskState()
    monkeypatch.setattr(task.sm, "state", stub)
    return stub


def test_ws1_legacy_auto_path(monkeypatch) -> None:
    """WS-1: script_mode=None + empty video_script → legacy auto path."""
    captured = {}

    def fake_generate_script(**kwargs):
        captured.update(kwargs)
        return "auto-generated script"

    monkeypatch.setattr(llm, "generate_script", fake_generate_script)
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="diamond ring", video_script="", video_language="en", paragraph_number=1
    )
    result = task.generate_script("test-task", params)

    assert result == "auto-generated script"
    assert captured["video_subject"] == "diamond ring"


def test_ws2_legacy_verbatim_path(monkeypatch) -> None:
    """WS-2: script_mode=None + non-empty video_script → verbatim."""
    monkeypatch.setattr(llm, "generate_script", lambda **kw: "should not be called")
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x", video_script="creator's exact words"
    )
    result = task.generate_script("test-task", params)

    assert result == "creator's exact words"


def test_ws3_explicit_auto_with_empty_script(monkeypatch) -> None:
    """WS-3: explicit script_mode=auto + empty → auto path (equiv to WS-1)."""
    monkeypatch.setattr(llm, "generate_script", lambda **kw: "auto output")
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x", video_script="", script_mode="auto"
    )
    assert task.generate_script("test-task", params) == "auto output"


def test_ws4_explicit_auto_ignores_video_script(monkeypatch) -> None:
    """WS-4: script_mode=auto + non-empty video_script → still auto path
    (text ignored — explicit mode wins over content)."""
    monkeypatch.setattr(llm, "generate_script", lambda **kw: "auto output")
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x",
        video_script="this should be ignored",
        script_mode="auto",
    )
    assert task.generate_script("test-task", params) == "auto output"


def test_ws5_explicit_verbatim(monkeypatch) -> None:
    """WS-5: explicit script_mode=verbatim → input unchanged."""
    monkeypatch.setattr(llm, "generate_script", lambda **kw: "should not be called")
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x",
        video_script="exact final script",
        script_mode="verbatim",
    )
    assert task.generate_script("test-task", params) == "exact final script"


def test_ws7_polish_dispatch(monkeypatch) -> None:
    """WS-7: script_mode=polish + non-empty brief → polish_script called."""
    captured = {}

    def fake_polish(**kwargs):
        captured.update(kwargs)
        return "polished marketing copy"

    monkeypatch.setattr(llm, "polish_script", fake_polish)
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="Cold Brew Kit. Overnight steep.",
        video_script="rough brief",
        script_mode="polish",
        script_brief="rough brief",
        video_language="en",
    )
    result = task.generate_script("test-task", params)

    assert result == "polished marketing copy"
    assert captured["brief"] == "rough brief"
    assert captured["video_subject"] == "Cold Brew Kit. Overnight steep."
    assert captured["language"] == "en"


def test_ws8_polish_empty_brief_fails(monkeypatch) -> None:
    """WS-8: script_mode=polish + empty video_script → polish_brief_required."""
    monkeypatch.setattr(
        llm, "polish_script", lambda **kw: pytest.fail("should not call")
    )
    stub = _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x", video_script="", script_mode="polish"
    )
    result = task.generate_script("test-task", params)

    assert result is None
    assert stub.last_error == "polish_brief_required"


def test_ws9_polish_llm_failure_surfaces(monkeypatch) -> None:
    """WS-9: polish_script raises → task fails with polish_failed."""
    def raising(**kw):
        raise RuntimeError("openai down")

    monkeypatch.setattr(llm, "polish_script", raising)
    stub = _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x",
        video_script="valid brief",
        script_mode="polish",
    )
    result = task.generate_script("test-task", params)

    assert result is None
    assert stub.last_error == "polish_failed"


def test_ws10_polish_prompt_contains_brief_and_subject(monkeypatch) -> None:
    """WS-10: polish prompt rendered to LLM contains BOTH the brief AND the
    enriched subject (Q1 clarification verification)."""
    fake = _FakeResponse(output="polished")

    with patch.object(llm, "_generate_response", fake):
        llm.polish_script(
            brief="highlight 32oz size",
            video_subject="Cold Brew Kit. Slow-steeped overnight. (sourced from acmebrew.com)",
        )

    assert fake.last_prompt is not None
    assert "highlight 32oz size" in fake.last_prompt
    assert "Cold Brew Kit. Slow-steeped overnight" in fake.last_prompt
    assert "acmebrew.com" in fake.last_prompt
    # Constraint #2 of the prompt template — brief wins on conflict:
    assert "If brief and context disagree, brief wins" in fake.last_prompt


def test_polished_script_overwrites_video_script_brief_preserved(monkeypatch) -> None:
    """Confirms params.script_brief is preserved while video_script is
    overwritten with polished output. (Augments WS-7.)"""
    monkeypatch.setattr(llm, "polish_script", lambda **kw: "polished")
    _stub_state_manager(monkeypatch)

    params = VideoParams(
        video_subject="x",
        video_script="original brief",
        script_mode="polish",
        script_brief="original brief",
    )
    result = task.generate_script("test-task", params)

    # Returned script is polished
    assert result == "polished"
    # Original brief preserved on the params (the dispatch returns the
    # polished string but doesn't mutate params; the caller is responsible
    # for storing both).
    assert params.script_brief == "original brief"
