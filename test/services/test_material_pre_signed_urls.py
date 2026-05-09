"""Spec 015 — material.py pre-signed URL fetch path (T020).

Covers the sidecar-driven branch added by FR-022. Mocks ``requests.get``
to avoid network. Cases MAT-1, MAT-5, MAT-6, MAT-7, MAT-10 from
contracts/material-pre-signed-urls.md §7.1. Other MAT-* cases are covered
indirectly by existing test_uploaded_visuals + test_visuals_wire_shape.
"""

from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.services import material


def _write_sidecar(task_root: Path, payload: dict) -> None:
    sidecar = task_root / "visuals.json"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def task_dir(monkeypatch, tmp_path: Path) -> Path:
    """Sandboxed task dir. Patch utils.task_dir to point here."""
    task_id = "tsk_test_001"
    root = tmp_path / "tasks" / task_id
    root.mkdir(parents=True)
    monkeypatch.setattr(material.utils, "task_dir", lambda _id: str(root))
    monkeypatch.chdir(tmp_path)
    return root


def _mock_response(status_code: int = 200, content: bytes = b"\xff\xd8\xfffake-mp4-bytes"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.iter_content = lambda chunk_size: [content]
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}", response=resp)
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    return resp


def test_mat1_two_pre_signed_urls_fetched(task_dir: Path) -> None:
    """MAT-1: sidecar with 2 URLs → 2 GET calls + 2 files in clips/."""
    _write_sidecar(task_dir, {
        "tenant_id": "demo-tenant-001",
        "user_id": "demo-user-001",
        "mode": "short",
        "visuals_mode": "auto",
        "user_uploaded_paths": [],
        "pre_signed_clip_urls": [
            "http://l2.test/_signed/abc/demo-tenant-001/clip-a.mp4?expires=999",
            "http://l2.test/_signed/def/demo-tenant-001/clip-b.mp4?expires=999",
        ],
    })

    with patch("app.services.material.requests.get") as mock_get:
        mock_get.return_value = _mock_response()
        out = material.download_videos(
            task_id="tsk_test_001",
            search_terms=["unused"],
        )

    assert len(out) == 2
    assert mock_get.call_count == 2
    # Verify files exist + named clip-1, clip-2
    files = sorted(os.listdir(task_dir / "clips"))
    assert files == ["clip-1.mp4", "clip-2.mp4"]


def test_mat5_url_returns_5xx_then_200_retries(task_dir: Path) -> None:
    """MAT-6: 5xx then 200 → retries successfully."""
    _write_sidecar(task_dir, {
        "tenant_id": "demo-tenant-001",
        "mode": "short",
        "visuals_mode": "auto",
        "user_uploaded_paths": [],
        "pre_signed_clip_urls": ["http://l2.test/_signed/abc/demo-tenant-001/clip.mp4?expires=999"],
    })

    responses = [_mock_response(status_code=503), _mock_response(status_code=200)]
    with patch("app.services.material.requests.get", side_effect=responses):
        out = material.download_videos(task_id="tsk_test_001", search_terms=["x"])

    assert len(out) == 1


def test_mat7_url_returns_5xx_twice_falls_back_to_placeholder(task_dir: Path) -> None:
    """MAT-7: 5xx twice → render salvages with a black-frame placeholder.

    Updated 2026-05-09 for spec 019 (FR-004): ``_download_from_pre_signed_urls``
    no longer raises ``RuntimeError("fetch_failed")`` when the retry budget is
    exhausted. Instead, it writes a black-frame MP4 placeholder for the failed
    segment so the render salvages with audio + subtitle alignment intact.
    The terminal-failure path (FR-006) is now: placeholder write itself fails
    (e.g. ffmpeg missing). That case is covered by
    ``test_material_url_expiry.py::test_placeholder_failure_is_terminal``.
    """
    _write_sidecar(task_dir, {
        "tenant_id": "demo-tenant-001",
        "mode": "short",
        "visuals_mode": "auto",
        "user_uploaded_paths": [],
        "pre_signed_clip_urls": ["http://l2.test/_signed/abc/demo-tenant-001/clip.mp4?expires=999"],
    })

    with patch(
        "app.services.material.requests.get",
        side_effect=[_mock_response(status_code=503), _mock_response(status_code=502)],
    ), patch(
        "app.services.material._write_black_frame_clip"
    ) as mock_placeholder:
        out = material.download_videos(task_id="tsk_test_001", search_terms=["x"])

    # FR-004: placeholder substituted; render returns the salvaged clip list.
    assert mock_placeholder.call_count == 1
    assert len(out) == 1, "Failed segment must be replaced by a placeholder, not dropped"


def test_mat10_order_preservation(task_dir: Path) -> None:
    """MAT-10: clip-1, clip-2, clip-3 align with URL order."""
    _write_sidecar(task_dir, {
        "tenant_id": "demo-tenant-001",
        "mode": "short",
        "visuals_mode": "auto",
        "user_uploaded_paths": [],
        "pre_signed_clip_urls": [
            "http://l2.test/_signed/aa/t/u1.mp4?expires=999",
            "http://l2.test/_signed/bb/t/u2.mp4?expires=999",
            "http://l2.test/_signed/cc/t/u3.mp4?expires=999",
        ],
    })

    with patch("app.services.material.requests.get") as mock_get:
        mock_get.return_value = _mock_response()
        out = material.download_videos(task_id="tsk_test_001", search_terms=["x"])

    files = sorted(os.listdir(task_dir / "clips"))
    assert files == ["clip-1.mp4", "clip-2.mp4", "clip-3.mp4"]


def test_pre_signed_path_completes_without_pexels_call(task_dir: Path) -> None:
    """Sanity: pre-signed branch never reaches Pexels (verified by no module
    network call beyond the patched ``requests.get``). Asset-audit emission
    is best-effort and depends on script.json being present (which the
    pipeline writes elsewhere) — not asserted here."""
    _write_sidecar(task_dir, {
        "tenant_id": "demo-tenant-001",
        "mode": "short",
        "visuals_mode": "auto",
        "user_uploaded_paths": [],
        "pre_signed_clip_urls": ["http://l2.test/_signed/abc/t/x.mp4?expires=999"],
    })

    with patch("app.services.material.requests.get") as mock_get, \
         patch("app.services.material.search_videos_pexels") as pexels, \
         patch("app.services.material.search_videos_pixabay") as pixabay:
        mock_get.return_value = _mock_response()
        out = material.download_videos(task_id="tsk_test_001", search_terms=["x"])

    assert len(out) == 1
    pexels.assert_not_called()
    pixabay.assert_not_called()
