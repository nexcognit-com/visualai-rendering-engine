"""Smoke tests for POST /api/v1/uploads/image (spec 006, IU-1..IU-10).

Synthetic images are generated via Pillow so no binary fixtures are shipped.
Tests are offline + fast (<2s total).
"""

from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.asgi import get_application
from app.utils import utils

client = TestClient(get_application())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_uploads():
    """Track and remove any test-created uploads at teardown."""
    created: list[str] = []
    yield created
    for path in created:
        try:
            os.remove(path)
        except OSError:
            pass


def _track_response(response, cleanup_list: list[str]) -> None:
    """Queue both original and cropped derivatives for cleanup."""
    if response.status_code != 200:
        return
    body = response.json()
    for key in ("path", "original_path"):
        if isinstance(body, dict) and isinstance(body.get(key), str):
            cleanup_list.append(os.path.join(utils.root_dir(), body[key]))


def _make_image(width: int, height: int, fmt: str = "JPEG", color="red") -> bytes:
    """Build an in-memory image of given size in given format."""
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format=fmt, quality=88 if fmt == "JPEG" else None)
    return buf.getvalue()


def _make_png_with_alpha(width: int, height: int) -> bytes:
    """Transparent PNG to exercise the alpha-flatten path."""
    img = Image.new("RGBA", (width, height), (255, 0, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# IU-1..IU-10
# ---------------------------------------------------------------------------


def test_iu1_happy_path_jpeg(cleanup_uploads) -> None:
    """IU-1: 4032x3024 JPEG → 200 with aspect-preserved downscale to 1920 long-side.

    Updated for Clarifications 2026-05-03 follow-up: NO 9:16 crop at upload.
    Expected output is 1920×1440 (4:3 preserved, longest side = 1920).
    """
    body = _make_image(4032, 3024, fmt="JPEG", color="red")
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("hero.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    _track_response(response, cleanup_uploads)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["mime_type"] == "image/jpeg"
    assert out["source_width_px"] == 4032
    assert out["source_height_px"] == 3024
    # Aspect 4:3 preserved; longest side = 1920.
    assert out["cropped_width_px"] == 1920
    assert out["cropped_height_px"] == 1440
    assert out["content_hash"].startswith("sha256:")
    assert out["path"].endswith(".cropped.jpg")
    assert out["original_path"].endswith(".jpg")
    # Both files exist
    assert os.path.exists(os.path.join(utils.root_dir(), out["path"]))
    assert os.path.exists(os.path.join(utils.root_dir(), out["original_path"]))


def test_iu1b_landscape_screenshot_preserved(cleanup_uploads) -> None:
    """IU-1b: 1648×892 landscape dashboard screenshot → output preserves the
    full image (no 70% horizontal loss to a center-strip crop).
    """
    body = _make_image(1648, 892, fmt="JPEG", color="blue")
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("dashboard.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    _track_response(response, cleanup_uploads)
    assert response.status_code == 200, response.text
    out = response.json()
    # Source already < 1920 long-side → no downscale either; full preservation.
    assert out["cropped_width_px"] == 1648
    assert out["cropped_height_px"] == 892


def test_iu2_png_with_transparency(cleanup_uploads) -> None:
    """IU-2: PNG with alpha → JPEG (alpha flattened to neutral fill)."""
    body = _make_png_with_alpha(2000, 3000)
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("logo.png", body, "image/png")},
        data={"role": "model"},
    )
    _track_response(response, cleanup_uploads)
    assert response.status_code == 200
    out = response.json()
    assert out["mime_type"] == "image/png"
    assert out["path"].endswith(".cropped.jpg")  # always re-encoded to JPEG
    # Aspect 2:3 preserved; longest side capped at 1920 → 1280×1920.
    assert out["cropped_width_px"] == 1280
    assert out["cropped_height_px"] == 1920


def test_iu3_oversize_rejected() -> None:
    """IU-3: 11 MB body → 413 file_too_large."""
    # Synthesize a >10 MB image quickly: large solid PNG won't compress small.
    big = _make_image(8000, 8000, fmt="PNG", color="red")
    # Pad if needed (PNG of solid color may compress under 10 MB; force size).
    if len(big) <= 10 * 1024 * 1024:
        big = big + b"\x00" * (11 * 1024 * 1024 - len(big))
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("big.png", big, "image/png")},
        data={"role": "product"},
    )
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["error_code"] == "file_too_large"


def test_iu4_unsupported_format() -> None:
    """IU-4: image/tiff MIME → 400 unsupported_format."""
    body = b"II*\x00" + b"\x00" * 100  # fake TIFF magic
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("scan.tiff", body, "image/tiff")},
        data={"role": "product"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "unsupported_format"


def test_iu5_corrupt_jpeg(cleanup_uploads) -> None:
    """IU-5: corrupt JPEG (truncated bytes) → 415 invalid_image, no orphans."""
    body = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 50  # truncated
    uploads_before = (
        set(os.listdir(os.path.join(utils.root_dir(), "storage", "uploads")))
        if os.path.isdir(os.path.join(utils.root_dir(), "storage", "uploads"))
        else set()
    )
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("broken.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "invalid_image"
    uploads_after = (
        set(os.listdir(os.path.join(utils.root_dir(), "storage", "uploads")))
        if os.path.isdir(os.path.join(utils.root_dir(), "storage", "uploads"))
        else set()
    )
    # No orphan files created from the failed write.
    assert uploads_before == uploads_after


def test_iu6_low_resolution_warning(cleanup_uploads) -> None:
    """IU-6: 600x400 → 200 with warning='low_resolution'."""
    body = _make_image(600, 400, fmt="JPEG", color="green")
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("small.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    _track_response(response, cleanup_uploads)
    assert response.status_code == 200
    out = response.json()
    assert out.get("warning") == "low_resolution"


def test_iu7_degenerate_dimensions() -> None:
    """IU-7: 2x2 image → 415 degenerate_dimensions (< 100 px)."""
    body = _make_image(2, 2, fmt="JPEG", color="red")
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("tiny.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "degenerate_dimensions"


def test_iu8_zip_bomb_caught() -> None:
    """IU-8: large pixel-count image → 415 degenerate_dimensions (>100MP guard).

    A 12000x12000 image is 144MP, exceeding the 100MP post-decode bomb guard.
    """
    body = _make_image(12000, 12000, fmt="JPEG", color="red")
    if len(body) > 10 * 1024 * 1024:
        # Compressed solid-color JPEG should be small. If it isn't, skip the
        # test rather than tripping the size limit instead.
        pytest.skip(f"synthetic image too large: {len(body)} bytes")
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("bomb.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "degenerate_dimensions"


def test_iu9_missing_role() -> None:
    """IU-9: missing role form field → 400 unsupported_role."""
    body = _make_image(2000, 3000)
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("hero.jpg", body, "image/jpeg")},
        # no `data={"role": ...}` — role omitted
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "unsupported_role"


def test_iu10_content_hash_correct(cleanup_uploads) -> None:
    """IU-10: SHA-256 hash matches hashlib.sha256(body).hexdigest()."""
    body = _make_image(2000, 3000, fmt="JPEG", color="blue")
    expected_hash = "sha256:" + hashlib.sha256(body).hexdigest()
    response = client.post(
        "/api/v1/uploads/image",
        files={"file": ("hero.jpg", body, "image/jpeg")},
        data={"role": "product"},
    )
    _track_response(response, cleanup_uploads)
    assert response.status_code == 200
    assert response.json()["content_hash"] == expected_hash
