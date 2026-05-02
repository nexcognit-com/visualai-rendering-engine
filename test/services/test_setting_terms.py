"""Tests for spec 006 hybrid mode — setting-tag two-pass (ST-1..ST-10).

Mocks llm._generate_response so tests are offline.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import llm
from app.services.llm import (
    _DEFAULT_SETTING_QUERIES,
    _VALID_SETTING_TAGS,
    expand_setting_to_queries,
    extract_setting_tag,
    generate_setting_terms,
)


# ---------------------------------------------------------------------------
# extract_setting_tag (ST-1..ST-4)
# ---------------------------------------------------------------------------


def _stub_response(value: str):
    """Build a _generate_response replacement returning a fixed string."""
    return lambda prompt: value


def test_st1_healthcare_script() -> None:
    """ST-1: clinic-themed script → 'healthcare'."""
    with patch.object(llm, "_generate_response", _stub_response("healthcare")):
        assert extract_setting_tag(
            "AI-powered patient triage for clinics. Reduce wait times by 50%."
        ) == "healthcare"


def test_st2_manufacturing_script() -> None:
    """ST-2: factory script → 'manufacturing'."""
    with patch.object(llm, "_generate_response", _stub_response("manufacturing")):
        assert extract_setting_tag(
            "Defect detection on the assembly line — catch issues at line speed."
        ) == "manufacturing"


def test_st3_empty_response_falls_back() -> None:
    """ST-3: LLM returns empty string → 'general'."""
    with patch.object(llm, "_generate_response", _stub_response("")):
        assert extract_setting_tag("Some script") == "general"


def test_st4_invalid_tag_falls_back() -> None:
    """ST-4: LLM returns out-of-allowlist tag → 'general'."""
    with patch.object(llm, "_generate_response", _stub_response("airspace")):
        assert extract_setting_tag("Aerospace inventory tracking") == "general"


def test_st4b_quotes_and_periods_stripped() -> None:
    """ST-4b: LLM returns the tag with surrounding noise — should still match."""
    with patch.object(llm, "_generate_response", _stub_response('"healthcare".')):
        assert extract_setting_tag("Hospital script") == "healthcare"


def test_st4c_empty_input_no_llm_call() -> None:
    """Empty/whitespace script → 'general' without making an LLM call."""
    fake_called = {"hit": False}

    def fake(prompt):
        fake_called["hit"] = True
        return "manufacturing"

    with patch.object(llm, "_generate_response", fake):
        assert extract_setting_tag("") == "general"
        assert extract_setting_tag("   \n\t  ") == "general"
    assert fake_called["hit"] is False


def test_st4d_llm_exception_falls_back() -> None:
    """LLM raises → falls back to 'general'."""
    def raising(prompt):
        raise RuntimeError("API down")

    with patch.object(llm, "_generate_response", raising):
        assert extract_setting_tag("Some script") == "general"


# ---------------------------------------------------------------------------
# expand_setting_to_queries (ST-5..ST-8)
# ---------------------------------------------------------------------------


def test_st5_manufacturing_queries() -> None:
    """ST-5: valid LLM JSON → 5 cleaned queries."""
    raw = '["A","B","C","D","E"]'
    with patch.object(llm, "_generate_response", _stub_response(raw)):
        out = expand_setting_to_queries("manufacturing")
    assert out == ["A", "B", "C", "D", "E"]


def test_st6_healthcare_queries_distinct() -> None:
    """ST-6: 5 distinct queries returned."""
    raw = '["clinic waiting room","doctor consultation","hospital corridor","medical staff team","patient receiving care"]'
    with patch.object(llm, "_generate_response", _stub_response(raw)):
        out = expand_setting_to_queries("healthcare")
    assert len(out) == 5
    assert len(set(out)) == 5


def test_st7_general_queries_office_lifestyle() -> None:
    """ST-7: general tag returns office/lifestyle defaults when LLM fails."""
    def raising(prompt):
        raise RuntimeError("rate limit")

    with patch.object(llm, "_generate_response", raising):
        out = expand_setting_to_queries("general")
    assert out == _DEFAULT_SETTING_QUERIES["general"]
    # Sanity-check the defaults are office/lifestyle in nature:
    assert "office" in " ".join(out).lower() or "people" in " ".join(out).lower()


def test_st8_malformed_json_falls_back_to_defaults() -> None:
    """ST-8: garbage response → returns defaults list."""
    with patch.object(llm, "_generate_response", _stub_response("not json at all")):
        out = expand_setting_to_queries("retail")
    assert out == _DEFAULT_SETTING_QUERIES["retail"]


def test_st8b_partial_list_padded_from_defaults() -> None:
    """LLM returns only 2 queries → padded to 5 from defaults."""
    raw = '["custom one","custom two"]'
    with patch.object(llm, "_generate_response", _stub_response(raw)):
        out = expand_setting_to_queries("manufacturing")
    assert len(out) == 5
    assert out[0] == "custom one"
    assert out[1] == "custom two"
    # Remaining slots filled from manufacturing defaults
    assert out[2] in _DEFAULT_SETTING_QUERIES["manufacturing"]


def test_st8c_unknown_tag_uses_general_defaults() -> None:
    """Pass an unknown tag → silently coerced to 'general'."""
    raw = '["q1","q2","q3","q4","q5"]'
    with patch.object(llm, "_generate_response", _stub_response(raw)):
        out = expand_setting_to_queries("nonsense_tag")
    # The LLM still gets called (with safe_tag=general in the prompt) — accept its 5 queries.
    assert out == ["q1", "q2", "q3", "q4", "q5"]


def test_st8d_markdown_codefence_stripped() -> None:
    """LLM wraps JSON in ``` fence → still parses."""
    raw = "```json\n[\"A\",\"B\",\"C\",\"D\",\"E\"]\n```"
    with patch.object(llm, "_generate_response", _stub_response(raw)):
        out = expand_setting_to_queries("office")
    assert out == ["A", "B", "C", "D", "E"]


# ---------------------------------------------------------------------------
# generate_setting_terms orchestrator (ST-9, ST-10)
# ---------------------------------------------------------------------------


def test_st9_orchestrator_returns_tuple() -> None:
    """ST-9: orchestrator returns (tag, queries[5]) on happy path."""
    responses = iter(["manufacturing", '["q1","q2","q3","q4","q5"]'])
    with patch.object(llm, "_generate_response", lambda prompt: next(responses)):
        tag, queries = generate_setting_terms("Factory floor automation")
    assert tag == "manufacturing"
    assert queries == ["q1", "q2", "q3", "q4", "q5"]


def test_st10_orchestrator_handles_failure() -> None:
    """ST-10: orchestrator falls back gracefully on LLM failure."""
    def raising(prompt):
        raise RuntimeError("network down")

    with patch.object(llm, "_generate_response", raising):
        tag, queries = generate_setting_terms("Some script")
    # First pass falls back to general; second pass falls back to defaults.
    assert tag == "general"
    assert queries == _DEFAULT_SETTING_QUERIES["general"]
    assert len(queries) == 5
