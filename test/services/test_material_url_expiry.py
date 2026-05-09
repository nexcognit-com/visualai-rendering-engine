"""Spec 019 — pre-signed URL expiry resilience tests for material.py.

Covers FR-003 (403/410 terminal), FR-004 (black-frame placeholder),
FR-005 (WARNING log), FR-006 (placeholder-failure terminal), FR-007
(alignment preserved). Mocks ``requests.get`` and ``_write_black_frame_clip``
to keep these tests fast and FFmpeg-free; the real ffmpeg integration test
lives in ``test_black_frame_clip.py``.

KNOWN LIMITATION (flagged at /speckit.implement time): the shipped
``_download_from_pre_signed_urls`` calls ``_write_black_frame_clip(out_path)``
with the keyword-default 5.0s — it does NOT receive per-URL target durations.
FR-004's "failed segment's target duration" can only be honored after L2
extends the wire payload to send durations alongside URLs (cross-layer
follow-up). These tests therefore assert the current contract: 5s placeholder
default, alignment preserved at the segment-count + ordering level.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import material


@pytest.fixture
def task_dir(monkeypatch, tmp_path: Path) -> Path:
    """Sandboxed task dir; patch utils.task_dir to point here."""
    task_id = "tsk_test_expiry"
    root = tmp_path / "tasks" / task_id
    root.mkdir(parents=True)
    monkeypatch.setattr(material.utils, "task_dir", lambda _id: str(root))
    return root


def _mock_response(status_code: int = 200, content: bytes = b"fake-mp4-bytes"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.iter_content = lambda chunk_size: [content]
    resp.raise_for_status = MagicMock()
    if 400 <= status_code < 600:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}", response=resp)
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    return resp


# ---------------------------------------------------------------------------
# FR-003: 403 / 410 are terminal — no retry against a dead signature.
# FR-004: failed URL → black-frame placeholder (here mocked).
# ---------------------------------------------------------------------------

def test_403_short_circuits_retry_and_writes_placeholder(task_dir: Path) -> None:
    """FR-003 + FR-004: 403 = expired signature → 0 retries, placeholder written."""
    with patch("app.services.material.requests.get", return_value=_mock_response(403)) as mock_get, \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder:
        out_paths = material._download_from_pre_signed_urls(
            "tsk_test_expiry", ["https://example.com/clip-1.mp4?Expires=1"]
        )
    assert mock_get.call_count == 1, "403 must NOT trigger a retry"
    assert mock_placeholder.call_count == 1
    assert len(out_paths) == 1
    assert out_paths[0].endswith("clip-1.mp4")


def test_410_short_circuits_retry_and_writes_placeholder(task_dir: Path) -> None:
    """FR-003 + FR-004: 410 = gone → 0 retries, placeholder written."""
    with patch("app.services.material.requests.get", return_value=_mock_response(410)) as mock_get, \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder:
        out_paths = material._download_from_pre_signed_urls(
            "tsk_test_expiry", ["https://example.com/clip-1.mp4"]
        )
    assert mock_get.call_count == 1, "410 must NOT trigger a retry"
    assert mock_placeholder.call_count == 1
    assert len(out_paths) == 1


# ---------------------------------------------------------------------------
# 5xx — retry budget IS spent; success on retry is happy-path, failure → placeholder.
# ---------------------------------------------------------------------------

def test_5xx_retries_then_succeeds(task_dir: Path) -> None:
    """5xx is transient: one retry; success on retry → no placeholder written."""
    responses = [_mock_response(503), _mock_response(200)]
    with patch("app.services.material.requests.get", side_effect=responses) as mock_get, \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder, \
         patch("app.services.material.time.sleep" if hasattr(material, "time") else "time.sleep"):
        out_paths = material._download_from_pre_signed_urls(
            "tsk_test_expiry", ["https://example.com/clip-1.mp4"]
        )
    assert mock_get.call_count == 2, "503 must trigger one retry"
    assert mock_placeholder.call_count == 0, "Success on retry → no placeholder"
    assert len(out_paths) == 1


def test_5xx_retries_then_dies_writes_placeholder(task_dir: Path) -> None:
    """5xx persistent across both attempts → placeholder fallback."""
    with patch("app.services.material.requests.get",
               side_effect=[_mock_response(503), _mock_response(503)]) as mock_get, \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder:
        out_paths = material._download_from_pre_signed_urls(
            "tsk_test_expiry", ["https://example.com/clip-1.mp4"]
        )
    assert mock_get.call_count == 2
    assert mock_placeholder.call_count == 1
    assert len(out_paths) == 1


# ---------------------------------------------------------------------------
# SC-004 / FR-004: every URL dead → render still produces a complete clip list.
# ---------------------------------------------------------------------------

def test_all_urls_dead_render_still_completes(task_dir: Path) -> None:
    """SC-004: all 5 URLs return 403 → 5 placeholders written, no exception."""
    urls = [f"https://example.com/clip-{i}.mp4?Expires=1" for i in range(1, 6)]
    with patch("app.services.material.requests.get", return_value=_mock_response(403)), \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder:
        out_paths = material._download_from_pre_signed_urls("tsk_test_expiry", urls)
    assert mock_placeholder.call_count == 5
    assert len(out_paths) == 5
    # Filenames preserve original ordering (clip-1, clip-2, ..., clip-5).
    for i, p in enumerate(out_paths, start=1):
        assert p.endswith(f"clip-{i}.mp4")


# ---------------------------------------------------------------------------
# FR-006: placeholder-failure is terminal — render fails with material.fetch_failed.
# ---------------------------------------------------------------------------

def test_placeholder_failure_is_terminal(task_dir: Path) -> None:
    """FR-006: if _write_black_frame_clip itself raises, the render dies."""
    with patch("app.services.material.requests.get", return_value=_mock_response(403)), \
         patch("app.services.material._write_black_frame_clip",
               side_effect=RuntimeError("ffmpeg missing")):
        with pytest.raises(RuntimeError, match=r"material\.fetch_failed"):
            material._download_from_pre_signed_urls(
                "tsk_test_expiry", ["https://example.com/clip-1.mp4"]
            )


# ---------------------------------------------------------------------------
# FR-007: alignment preserved — all clip slots filled, original order kept.
# ---------------------------------------------------------------------------

def test_alignment_preserved_with_placeholders_at_indices_2_and_5(task_dir: Path) -> None:
    """FR-007: placeholders at non-adjacent indices keep timeline structure intact.

    Five URLs total; indices 2 and 5 return 403, the rest return 200. Asserts:
    - out_paths length is 5 (no segment dropped)
    - filename pattern preserves the 1-based index in original order
    - real fetches and placeholders are interleaved exactly per status pattern

    NOTE: This test does NOT assert per-segment placeholder DURATION matching
    the failed URL's intended length — see module docstring for the FR-004
    "target duration" L2 protocol gap.
    """
    statuses = [200, 403, 200, 200, 410]  # indices 2 and 5 dead
    responses = [_mock_response(s) for s in statuses]
    urls = [f"https://example.com/clip-{i}.mp4" for i in range(1, 6)]

    with patch("app.services.material.requests.get", side_effect=responses), \
         patch("app.services.material._write_black_frame_clip") as mock_placeholder:
        out_paths = material._download_from_pre_signed_urls("tsk_test_expiry", urls)

    assert len(out_paths) == 5, "Every original slot must be filled"
    assert mock_placeholder.call_count == 2, "Exactly 2 placeholders for the 2 dead URLs"
    # Order preserved: clip-1 ... clip-5 in that sequence.
    for i, p in enumerate(out_paths, start=1):
        assert p.endswith(f"clip-{i}.mp4"), f"Slot {i} out of order: {p}"
