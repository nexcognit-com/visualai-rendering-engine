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


# ---------------------------------------------------------------------------
# Spec 019 — POST /api/v1/uploads/selfie MIME handling (FR-008, FR-009, FR-010)
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402  (intentional placement to keep image tests at top)
import shutil as _shutil  # noqa: E402
import subprocess as _subprocess  # noqa: E402


class TestSelfieUploadMimeStripping:
    """T012 — MIME parameter-stripping table (FR-008) + original-MIME echo (FR-010).

    These tests stub out post-MIME validation (probe / face-detect / slot
    eviction / persist) so they isolate the MIME-validation contract.
    """

    @staticmethod
    def _patch_post_mime_chain(monkeypatch, tmp_path):
        """Stub probe + face_detect + slot allocation so the MIME path runs
        in isolation. Returns the captured ffmpeg invocation count.
        """
        fake_meta = {"duration_s": 10.0, "fps": 30.0, "width": 720, "height": 1280}
        monkeypatch.setattr("app.controllers.v1.uploads._probe_selfie_metadata", lambda _: fake_meta)
        monkeypatch.setattr(
            "app.services.lip_sync.detect_face",
            lambda _: {"x": 100, "y": 100, "w": 200, "h": 200, "confidence": 0.95, "face_count": 1},
        )
        monkeypatch.setattr(
            "app.controllers.v1.uploads._evict_oldest_avatar_if_full", lambda _tenant: 1
        )
        monkeypatch.setattr(
            "app.utils.utils.tenant_avatar_dir",
            lambda *args, **kwargs: str(tmp_path),
        )
        monkeypatch.setattr("app.utils.utils.root_dir", lambda: str(tmp_path.parent))
        # Replace the ffmpeg subprocess.run with a tiny stub that just
        # touches the target file so the rest of the handler keeps going.
        original_run = _subprocess.run

        def _fake_run(cmd, **kw):
            # cmd[-1] is the output path for the re-encode invocation.
            target = cmd[-1]
            with open(target, "wb") as f:
                f.write(b"fake-mp4-bytes-for-test")
            return _subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("app.controllers.v1.uploads.subprocess.run", _fake_run)
        return original_run

    # --- Accept cases (parameter stripped) ---

    @pytest.mark.parametrize(
        "content_type",
        [
            "video/webm;codecs=vp8",
            "video/webm; codecs=vp9",
            "video/webm;codecs=vp8,opus",
            "video/x-matroska;codecs=h264",
        ],
    )
    def test_video_webm_codec_variants_accepted(
        self, monkeypatch, tmp_path, content_type
    ) -> None:
        """FR-008: codec-suffixed video MIMEs strip to the allow-list entry."""
        self._patch_post_mime_chain(monkeypatch, tmp_path)
        response = client.post(
            "/api/v1/uploads/selfie",
            files={"file": ("selfie.webm", b"fake-webm-bytes", content_type)},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "path" in body, f"Expected 'path' key in response, got {body}"
        # Persisted file is always .mp4 (canonical form).
        assert body["path"].endswith(".mp4")

    # --- Reject cases (FR-010 — original MIME echoed verbatim) ---

    def test_image_png_rejected_with_original_mime_echoed(self) -> None:
        """FR-010: PNG (no codec param) → 400 with the exact MIME echoed."""
        response = client.post(
            "/api/v1/uploads/selfie",
            files={"file": ("not-a-selfie.png", b"\x89PNG", "image/png")},
        )
        assert response.status_code == 400
        body = response.json()["detail"]
        assert body["error_code"] == "format_unsupported"
        assert body["message"] == "Unsupported MIME: image/png"

    def test_unknown_mime_with_codec_param_rejected_with_full_original_echoed(
        self,
    ) -> None:
        """FR-010: x-flv with codec param → 400 echoes the FULL original string,
        not the parameter-stripped form (so the creator can debug their client).
        """
        response = client.post(
            "/api/v1/uploads/selfie",
            files={"file": ("weird.flv", b"FLV-bytes", "video/x-flv;codecs=h263+")},
        )
        assert response.status_code == 400
        body = response.json()["detail"]
        assert body["error_code"] == "format_unsupported"
        # Must echo the full original (with codec param), not just "video/x-flv".
        assert "video/x-flv;codecs=h263+" in body["message"]


@pytest.mark.skipif(
    _shutil.which("ffmpeg") is None or _shutil.which("ffprobe") is None,
    reason="ffmpeg / ffprobe not on PATH",
)
class TestSelfieReencodeRoundTrip:
    """T013 — real ffmpeg round-trip for non-MP4 inputs (FR-009).

    Stubs probe + face_detect (synthetic color clips have no face) but lets
    the real upload_selfie ffmpeg re-encode run. Then ffprobes the persisted
    output and asserts the FR-009 contract: H.264 / yuv420p / no audio.
    """

    @pytest.mark.parametrize(
        ("content_type", "ext", "vcodec"),
        [
            ("video/webm;codecs=vp8", ".webm", "libvpx"),
            ("video/x-matroska;codecs=h264", ".mkv", "libx264"),
        ],
    )
    def test_non_mp4_persisted_as_h264_mp4_no_audio(
        self, monkeypatch, tmp_path, content_type, ext, vcodec
    ) -> None:
        # Build a tiny synthetic input clip via ffmpeg lavfi.
        src = tmp_path / f"src{ext}"
        _subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=30",
                "-c:v", vcodec,
                str(src),
            ],
            check=True, capture_output=True, text=True,
        )
        body = src.read_bytes()
        assert len(body) > 0

        # Stub probe + face detect; let the real ffmpeg re-encode run.
        fake_meta = {"duration_s": 10.0, "fps": 30.0, "width": 720, "height": 1280}
        monkeypatch.setattr(
            "app.controllers.v1.uploads._probe_selfie_metadata",
            lambda _: fake_meta,
        )
        monkeypatch.setattr(
            "app.services.lip_sync.detect_face",
            lambda _: {"x": 100, "y": 100, "w": 200, "h": 200, "confidence": 0.95, "face_count": 1},
        )
        slot_dir = tmp_path / "slot"
        slot_dir.mkdir()
        monkeypatch.setattr(
            "app.controllers.v1.uploads._evict_oldest_avatar_if_full", lambda _tenant: 1
        )
        monkeypatch.setattr(
            "app.utils.utils.tenant_avatar_dir",
            lambda *args, **kwargs: str(slot_dir),
        )
        monkeypatch.setattr("app.utils.utils.root_dir", lambda: str(tmp_path))

        response = client.post(
            "/api/v1/uploads/selfie",
            files={"file": (f"selfie{ext}", body, content_type)},
        )
        assert response.status_code == 200, response.text
        out = response.json()
        persisted = os.path.join(str(tmp_path), out["path"])
        assert os.path.exists(persisted), f"Persisted file missing: {persisted}"

        # FR-009 contract: probe the persisted MP4.
        probe = _subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", persisted],
            check=True, capture_output=True, text=True,
        )
        streams = _json.loads(probe.stdout)["streams"]
        # No audio track (FR-009 — re-encode drops audio).
        assert all(s["codec_type"] != "audio" for s in streams), \
            f"FR-009: audio track must be dropped, got streams={streams}"
        # Exactly one video stream, H.264 / yuv420p.
        video = [s for s in streams if s["codec_type"] == "video"]
        assert len(video) == 1
        assert video[0]["codec_name"] == "h264"
        assert video[0]["pix_fmt"] == "yuv420p"
