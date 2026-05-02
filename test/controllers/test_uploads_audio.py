"""Smoke tests for POST /api/v1/uploads/audio (spec 010, AU-1..AU-8).

Synthetic audio fixtures are generated via test_helpers.make_synthetic_audio()
so we don't ship binary blobs. ffmpeg + ffprobe are hard system requirements
per the constitution; tests assume they're on PATH.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.asgi import get_application
from app.utils import utils
from test.services.test_helpers import make_synthetic_audio

client = TestClient(get_application())


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


@pytest.fixture
def audio_factory(tmp_path: Path):
    """Produce synthetic audio files in tmp_path."""

    def _make(format: str, duration_s: float = 1.0, name: str | None = None) -> Path:
        ext = "wav" if format == "wav" else format
        out = tmp_path / (name or f"smoke.{ext}")
        make_synthetic_audio(out, duration_s=duration_s, format=format)
        return out

    return _make


def _track_response(response, cleanup_list: list[str]) -> None:
    """If the response wrote a file under storage/uploads, queue it for cleanup."""
    if response.status_code == 200 or response.status_code == 201:
        body = response.json()
        if isinstance(body, dict) and "path" in body:
            full = os.path.join(utils.root_dir(), body["path"])
            cleanup_list.append(full)


def test_au1_valid_wav(audio_factory, cleanup_uploads) -> None:
    """AU-1: valid 1 s WAV ≤ 10 MB → 201 with path + duration ≈ 1.0."""
    f = audio_factory("wav", duration_s=1.0)
    with open(f, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("smoke.wav", fh, "audio/wav")},
        )
    _track_response(response, cleanup_uploads)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].startswith("storage/uploads/")
    assert body["path"].endswith(".wav")
    assert body["mime_type"] == "audio/wav"
    assert 0.9 <= body["duration_seconds"] <= 1.1


def test_au2_valid_mp3(audio_factory, cleanup_uploads) -> None:
    """AU-2: valid MP3 → .mp3 extension stored, duration probed."""
    f = audio_factory("mp3", duration_s=1.0)
    with open(f, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("smoke.mp3", fh, "audio/mpeg")},
        )
    _track_response(response, cleanup_uploads)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].endswith(".mp3")
    assert 0.9 <= body["duration_seconds"] <= 1.2


def test_au3_valid_ogg(audio_factory, cleanup_uploads) -> None:
    """AU-3: valid OGG → .ogg extension."""
    f = audio_factory("ogg", duration_s=1.0)
    with open(f, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("smoke.ogg", fh, "audio/ogg")},
        )
    _track_response(response, cleanup_uploads)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].endswith(".ogg")


def test_au4_valid_m4a(audio_factory, cleanup_uploads) -> None:
    """AU-4: valid M4A → .m4a extension."""
    f = audio_factory("m4a", duration_s=1.0)
    with open(f, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("smoke.m4a", fh, "audio/mp4")},
        )
    _track_response(response, cleanup_uploads)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].endswith(".m4a")


def test_au5_file_too_large(tmp_path: Path) -> None:
    """AU-5: 12 MB body → 413 file_too_large."""
    big = tmp_path / "big.mp3"
    # 12 MB of fake bytes (no need to be valid audio — size check fires first).
    big.write_bytes(b"\x00" * (12 * 1024 * 1024))

    with open(big, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("big.mp3", fh, "audio/mpeg")},
        )
    assert response.status_code == 413
    body = response.json()
    assert body["detail"]["error_code"] == "file_too_large"


def test_au6_unsupported_format(tmp_path: Path) -> None:
    """AU-6: .flac upload (unsupported MIME) → 400 unsupported_format."""
    fake = tmp_path / "bad.flac"
    fake.write_bytes(b"fake flac bytes")

    with open(fake, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("bad.flac", fh, "audio/flac")},
        )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "unsupported_format"


def test_au7_corrupt_audio_cleanup(tmp_path: Path) -> None:
    """AU-7: bytes claiming audio MIME but unreadable → 415 + cleanup.

    The endpoint persists then probes; on probe failure it MUST delete the
    persisted file so storage/uploads/ doesn't leak orphans.
    """
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"this is not an mp3 file at all just plain text")

    upload_dir = utils.storage_dir("uploads", create=True)
    before = set(os.listdir(upload_dir))

    with open(bad, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("broken.mp3", fh, "audio/mpeg")},
        )
    assert response.status_code == 415
    body = response.json()
    assert body["detail"]["error_code"] == "invalid_audio"

    # No new orphan file should have leaked.
    after = set(os.listdir(upload_dir))
    new_files = after - before
    assert not new_files, f"orphan files leaked after rejection: {new_files}"


def test_au8_filename_path_traversal_safe(audio_factory, cleanup_uploads) -> None:
    """AU-8: path-traversal filename → response stored under UUID4 only."""
    f = audio_factory("wav", duration_s=1.0)
    with open(f, "rb") as fh:
        response = client.post(
            "/api/v1/uploads/audio",
            files={"file": ("../../etc/passwd.wav", fh, "audio/wav")},
        )
    _track_response(response, cleanup_uploads)

    assert response.status_code == 200, response.text
    body = response.json()
    # Stored path MUST be storage/uploads/<uuid>.wav — NO etc/passwd, no ../.
    assert body["path"].startswith("storage/uploads/")
    assert "etc" not in body["path"]
    assert ".." not in body["path"]
    assert body["path"].endswith(".wav")
