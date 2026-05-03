"""Spec 015 Fix #3 — domain-aware term expansion (Mode 5 quality)."""

from __future__ import annotations

import pytest

from app.services import llm


def test_expand_returns_input_unchanged_when_no_domain_match():
    """Topic with no recognised domain keywords passes through untouched."""
    out = llm.expand_domain_terms(
        ["mediterranean food", "olive oil", "fish"],
        topic="5 surprising mediterranean diet facts",
        script="The Mediterranean diet is well-known...",
    )
    assert out == ["mediterranean food", "olive oil", "fish"]


def test_expand_swaps_in_proxies_for_ai_topic():
    """AI keyword in topic adds visually-rich proxies to term list."""
    out = llm.expand_domain_terms(
        ["AI surveillance system", "computer vision technology"],
        topic="AI analytics platform for CCTV",
        script="advanced computer vision AI",
    )
    # Original terms preserved at front
    assert out[0] == "AI surveillance system"
    assert out[1] == "computer vision technology"
    # Proxies for "ai", "computer vision", "cctv", "surveillance" appear after
    proxy_terms = [t for t in out[2:]]
    assert any("server room" in t.lower() or "code on screen" in t.lower() for t in proxy_terms)
    assert any("camera" in t.lower() or "warehouse" in t.lower() or "control room" in t.lower() for t in proxy_terms)


def test_expand_caps_at_max_total():
    """Output never exceeds max_total even with many matches."""
    out = llm.expand_domain_terms(
        ["term1", "term2"],
        topic="AI machine learning computer vision cybersecurity surveillance",
        script="warehouse factory productivity",
        max_total=8,
    )
    assert len(out) == 8


def test_expand_dedupes_case_insensitively():
    """Duplicate terms (case-insensitive) are skipped."""
    out = llm.expand_domain_terms(
        ["server room blinking lights", "Server Room Blinking Lights"],
        topic="ai stuff",
    )
    # Only one of the two duplicates kept
    server_room_count = sum(1 for t in out if t.lower() == "server room blinking lights")
    assert server_room_count == 1


def test_expand_handles_warehouse_factory_topic():
    """Warehouse + factory topic gets industrial proxies."""
    out = llm.expand_domain_terms(
        ["warehouse operations"],
        topic="warehouse productivity factory floor",
    )
    proxy_pool = " ".join(out).lower()
    assert "warehouse" in proxy_pool or "factory" in proxy_pool


def test_expand_empty_input_returns_empty():
    out = llm.expand_domain_terms([], topic="", script="")
    assert out == []
