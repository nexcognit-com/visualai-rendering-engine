"""Spec 015 — Mode 5 research-then-write helpers (llm.research_topic +
llm.generate_faceless_script_grounded).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import llm


# --- research_topic ----------------------------------------------------------


def test_research_topic_returns_snippets_on_success():
    """Happy path: DDGS returns 3 results → 3 snippet strings."""
    fake_results = [
        {"title": "Mediterranean diet 101", "body": "Olive oil, fish, vegetables."},
        {"title": "5 facts", "body": "Lower heart disease rates."},
        {"title": "Studies", "body": "Linked to longer lifespan."},
    ]
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__ = MagicMock(return_value=fake_ddgs)
    fake_ddgs.__exit__ = MagicMock(return_value=False)
    fake_ddgs.text = MagicMock(return_value=iter(fake_results))

    with patch("ddgs.DDGS", return_value=fake_ddgs):
        out = llm.research_topic("Mediterranean diet")

    assert len(out) == 3
    assert "Mediterranean diet 101" in out[0]
    assert "Olive oil" in out[0]


def test_research_topic_returns_empty_on_search_failure():
    """Network / lib error → empty list (graceful degradation)."""
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__ = MagicMock(return_value=fake_ddgs)
    fake_ddgs.__exit__ = MagicMock(return_value=False)
    fake_ddgs.text = MagicMock(side_effect=RuntimeError("network down"))

    with patch("ddgs.DDGS", return_value=fake_ddgs):
        out = llm.research_topic("any topic")

    assert out == []


def test_research_topic_caps_each_snippet_at_280_chars():
    """Long snippets get truncated."""
    long_body = "x" * 1000
    fake_results = [{"title": "T", "body": long_body}]
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__ = MagicMock(return_value=fake_ddgs)
    fake_ddgs.__exit__ = MagicMock(return_value=False)
    fake_ddgs.text = MagicMock(return_value=iter(fake_results))

    with patch("ddgs.DDGS", return_value=fake_ddgs):
        out = llm.research_topic("x")

    assert len(out) == 1
    assert len(out[0]) == 280


def test_research_topic_skips_empty_results():
    """DDGS sometimes returns dicts with no title or body — skip those."""
    fake_results = [
        {"title": "", "body": ""},
        {"title": "Real", "body": "content"},
        {"title": None, "body": None},
    ]
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__ = MagicMock(return_value=fake_ddgs)
    fake_ddgs.__exit__ = MagicMock(return_value=False)
    fake_ddgs.text = MagicMock(return_value=iter(fake_results))

    with patch("ddgs.DDGS", return_value=fake_ddgs):
        out = llm.research_topic("x")

    assert len(out) == 1
    assert "Real" in out[0]


# --- generate_faceless_script_grounded ---------------------------------------


def test_grounded_script_uses_facts_when_provided():
    """Facts present → grounded prompt → response returned."""
    facts = ["Olive oil consumption is high.", "Fish 2x/week is typical."]
    with patch("app.services.llm._generate_response", return_value="A grounded script.") as gr:
        out = llm.generate_faceless_script_grounded(
            topic="Mediterranean diet", facts=facts
        )
    assert out == "A grounded script."
    # The prompt sent to the LLM must include the facts block
    sent_prompt = gr.call_args.kwargs["prompt"]
    assert "Olive oil" in sent_prompt
    assert "Fish 2x/week" in sent_prompt


def test_grounded_script_falls_back_to_ungrounded_when_no_facts():
    """Empty facts → delegates to llm.generate_script (existing path)."""
    with patch("app.services.llm.generate_script", return_value="ungrounded") as fb:
        out = llm.generate_faceless_script_grounded(topic="x", facts=[])
    assert out == "ungrounded"
    fb.assert_called_once()


def test_grounded_script_falls_back_when_llm_returns_empty():
    """If the LLM exhausts retries with empty response, falls back to ungrounded."""
    with patch("app.services.llm._generate_response", return_value=""), \
         patch("app.services.llm.generate_script", return_value="fallback") as fb:
        out = llm.generate_faceless_script_grounded(
            topic="x", facts=["one fact"]
        )
    assert out == "fallback"
    fb.assert_called_once()


# --- faceless.generate_script wiring -----------------------------------------


def test_faceless_generate_script_calls_research_then_grounded():
    """Mode 5's generate_script orchestrates research → grounded generation."""
    from app.models.schema import VideoParams
    from app.services.modes import faceless

    params = VideoParams(
        video_subject="space facts",
        mode="faceless",
        video_language="en",
    )
    with patch("app.services.modes.faceless.llm.research_topic", return_value=["fact 1", "fact 2"]) as rt, \
         patch("app.services.modes.faceless.llm.generate_faceless_script_grounded", return_value="script") as gen:
        out = faceless.generate_script(params)

    assert out == "script"
    rt.assert_called_once_with("space facts")
    # generate_faceless_script_grounded received the facts
    kwargs = gen.call_args.kwargs
    assert kwargs["facts"] == ["fact 1", "fact 2"]
    assert kwargs["topic"] == "space facts"
