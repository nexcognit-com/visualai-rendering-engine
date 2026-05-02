"""Smoke tests for spec 010 music configuration paths.

Validates the wire-shape contract in
``specs/010-music-control/contracts/music-config-contract.md`` against
the existing MPT BGM mixing pipeline. Most tests construct a
``VideoParams`` instance and assert validation behavior. Tests that need
a real render are deferred to ``quickstart.md`` manual verification —
unit smoke tests stop at the schema boundary.
"""

from __future__ import annotations

import pytest

from app.models.schema import VideoParams


def test_mc1_zero_regression_default_path() -> None:
    """MC-1: VideoParams without bgm_* fields uses the existing defaults.

    Confirms FR-010 + SC-007 — legacy callers / non-VisualAI clients see
    no change in behavior.
    """
    params = VideoParams(video_subject="test")

    assert params.bgm_type == "random"
    assert params.bgm_file == ""
    assert params.bgm_volume == 0.2


def test_mc2_random_preset_path() -> None:
    """MC-2: bgm_type='random' + default volume validates cleanly."""
    params = VideoParams(
        video_subject="test",
        bgm_type="random",
        bgm_volume=0.2,
    )

    assert params.bgm_type == "random"
    assert params.bgm_volume == 0.2


def test_mc3_specific_bundled_track() -> None:
    """MC-3: bgm_type='file' + bundled track path + custom volume validates."""
    params = VideoParams(
        video_subject="test",
        bgm_type="file",
        bgm_file="resource/songs/output005.mp3",
        bgm_volume=0.5,
    )

    assert params.bgm_type == "file"
    assert params.bgm_file == "resource/songs/output005.mp3"
    assert params.bgm_volume == 0.5


def test_mc5_voiceover_only_path() -> None:
    """MC-5: bgm_type='' produces a voiceover-only render.

    The pipeline's get_bgm_file() short-circuits on empty bgm_type and
    returns no BGM clip — see app/services/video.py:185-190.
    """
    params = VideoParams(
        video_subject="test",
        bgm_type="",
    )

    assert params.bgm_type == ""


def test_mc4_custom_upload_path_validates() -> None:
    """MC-4: custom uploads at storage/uploads/<uuid>.mp3 validate cleanly.

    A real render-time test would take 90+ seconds; this asserts the schema
    layer accepts the upload path shape. Real-render verification is in
    quickstart.md Part 4 (manual).
    """
    params = VideoParams(
        video_subject="test",
        bgm_type="file",
        bgm_file="storage/uploads/abc-123-def-456.mp3",
        bgm_volume=0.3,
    )
    assert params.bgm_file == "storage/uploads/abc-123-def-456.mp3"


def test_mc7_brand_library_forward_compat() -> None:
    """MC-7: bgm_file accepts future Brand Library path (FR-009, SC-006).

    Validates the schema-level forward-compatibility — the path doesn't
    need to exist for the model to accept it.
    """
    params = VideoParams(
        video_subject="test",
        bgm_type="file",
        bgm_file="brand-library/tenant_abc/music/intro_v3.mp3",
        bgm_volume=0.4,
    )

    assert params.bgm_file == "brand-library/tenant_abc/music/intro_v3.mp3"


@pytest.mark.parametrize(
    "bgm_type,bgm_file",
    [
        ("random", ""),
        ("file", "resource/songs/output005.mp3"),
        ("file", "storage/uploads/abc-123.mp3"),
        ("", ""),
    ],
)
def test_all_legal_wizard_payloads_validate(bgm_type: str, bgm_file: str) -> None:
    """Sanity check: every wire-shape variant the wizard might emit validates."""
    params = VideoParams(
        video_subject="test",
        bgm_type=bgm_type,
        bgm_file=bgm_file,
        bgm_volume=0.3,
    )
    assert params.bgm_type == bgm_type
    assert params.bgm_file == bgm_file
