"""Schema validation tests for spec 006 — VW-1..VW-10.

Covers VideoParams.visuals_mode + uploaded_*_paths + the
@model_validator(mode="after") that enforces the user_uploaded contract.

All tests are pure Pydantic — no LLM, network, or filesystem I/O. The
path-traversal tests use synthetic paths under ``storage/uploads/``
which we create + clean up around the suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.schema import VideoParams


# ---------------------------------------------------------------------------
# Filesystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def uploads_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a real ``storage/uploads/`` dir + chdir there so the
    realpath check in _require_under_uploads resolves correctly."""
    repo_root = tmp_path
    (repo_root / "storage" / "uploads").mkdir(parents=True)
    monkeypatch.chdir(repo_root)
    return repo_root / "storage" / "uploads"


def _touch(path: Path) -> str:
    """Create an empty file at path; return path relative to cwd."""
    path.write_bytes(b"\x00")
    return os.path.relpath(path, os.getcwd())


# ---------------------------------------------------------------------------
# VW-1..VW-10
# ---------------------------------------------------------------------------


def test_vw1_legacy_default() -> None:
    """VW-1: request with no visuals_mode → all three fields default cleanly."""
    p = VideoParams(video_subject="x")
    assert p.visuals_mode is None
    assert p.uploaded_model_path is None
    assert p.uploaded_product_paths == []
    # Legacy clients shouldn't see these fields when serialising with exclude_none:
    dumped = p.model_dump(exclude_none=True)
    assert "visuals_mode" not in dumped
    assert "uploaded_model_path" not in dumped
    # uploaded_product_paths is List[str] = [] not None — included in dump but
    # legacy callers ignore it.


def test_vw2_explicit_auto(uploads_dir: Path) -> None:
    """VW-2: explicit visuals_mode='auto' is valid; no path validation runs."""
    p = VideoParams(video_subject="x", visuals_mode="auto")
    assert p.visuals_mode == "auto"
    # Even with bogus paths, auto mode skips path checks:
    p2 = VideoParams(
        video_subject="x",
        visuals_mode="auto",
        uploaded_product_paths=["/anything/at/all"],
    )
    assert p2.visuals_mode == "auto"


def test_vw3_user_uploaded_one_product(uploads_dir: Path) -> None:
    """VW-3: user_uploaded + 1 product path → valid."""
    p1 = _touch(uploads_dir / "abc.cropped.jpg")
    p = VideoParams(
        video_subject="x",
        visuals_mode="user_uploaded",
        uploaded_product_paths=[p1],
    )
    assert p.visuals_mode == "user_uploaded"
    assert p.uploaded_product_paths == [p1]


def test_vw4_user_uploaded_three_products(uploads_dir: Path) -> None:
    """VW-4: user_uploaded + 3 product paths → valid."""
    paths = [_touch(uploads_dir / f"p{i}.cropped.jpg") for i in range(3)]
    p = VideoParams(
        video_subject="x",
        visuals_mode="user_uploaded",
        uploaded_product_paths=paths,
    )
    assert p.uploaded_product_paths == paths


def test_vw5_no_product_assets() -> None:
    """VW-5: user_uploaded + empty product paths → no_product_assets."""
    with pytest.raises(ValidationError, match="no_product_assets"):
        VideoParams(
            video_subject="x",
            visuals_mode="user_uploaded",
            uploaded_product_paths=[],
        )


def test_vw6_too_many_product_assets(uploads_dir: Path) -> None:
    """VW-6: user_uploaded + 4 product paths → too_many_product_assets."""
    paths = [_touch(uploads_dir / f"p{i}.cropped.jpg") for i in range(4)]
    with pytest.raises(ValidationError, match="too_many_product_assets"):
        VideoParams(
            video_subject="x",
            visuals_mode="user_uploaded",
            uploaded_product_paths=paths,
        )


def test_vw7_path_traversal_rejected(uploads_dir: Path) -> None:
    """VW-7: traversal attempt → path_outside_uploads."""
    # The traversal target wouldn't resolve under storage/uploads/.
    bogus = "../../etc/passwd"
    with pytest.raises(ValidationError, match="path_outside_uploads"):
        VideoParams(
            video_subject="x",
            visuals_mode="user_uploaded",
            uploaded_product_paths=[bogus],
        )


def test_vw8_invalid_literal() -> None:
    """VW-8: visuals_mode='random' rejected by Pydantic Literal."""
    with pytest.raises(ValidationError):
        VideoParams(video_subject="x", visuals_mode="random")  # type: ignore[arg-type]


def test_vw9_model_without_products(uploads_dir: Path) -> None:
    """VW-9: user_uploaded with model image but no products → no_product_assets.

    Per FR-003 + US2 AS-3: 'A product image is required. The model image
    alone cannot tell your product story.'
    """
    model_path = _touch(uploads_dir / "model.cropped.jpg")
    with pytest.raises(ValidationError, match="no_product_assets"):
        VideoParams(
            video_subject="x",
            visuals_mode="user_uploaded",
            uploaded_model_path=model_path,
            uploaded_product_paths=[],
        )


def test_vw11_hybrid_with_products_valid(uploads_dir: Path) -> None:
    """VW-11 (hybrid): user_uploaded-equivalent validation runs for hybrid mode."""
    paths = [_touch(uploads_dir / f"p{i}.cropped.jpg") for i in range(2)]
    p = VideoParams(
        video_subject="x",
        visuals_mode="hybrid",
        uploaded_product_paths=paths,
    )
    assert p.visuals_mode == "hybrid"
    assert p.uploaded_product_paths == paths


def test_vw12_hybrid_zero_products_rejected() -> None:
    """VW-12 (hybrid): hybrid + empty product paths → no_product_assets."""
    with pytest.raises(ValidationError, match="no_product_assets"):
        VideoParams(
            video_subject="x",
            visuals_mode="hybrid",
            uploaded_product_paths=[],
        )


def test_vw10_auto_keeps_cached_uploads(uploads_dir: Path) -> None:
    """VW-10: visuals_mode='auto' + non-empty uploaded_product_paths is valid.

    Supports US3 — when a user toggles My-assets → Auto, the wizard caches
    the uploaded paths but downloads_videos ignores them. The schema must
    accept this state (validator only enforces when mode=='user_uploaded').
    """
    paths = [_touch(uploads_dir / f"p{i}.cropped.jpg") for i in range(2)]
    p = VideoParams(
        video_subject="x",
        visuals_mode="auto",
        uploaded_product_paths=paths,
    )
    assert p.visuals_mode == "auto"
    assert p.uploaded_product_paths == paths
