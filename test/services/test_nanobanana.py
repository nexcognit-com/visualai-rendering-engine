"""Spec 015 — NanoBanana FAL.ai client (Mode 5 hero-image supplement)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import nanobanana


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-key-id:test-key-secret")
    yield


def _ok_response(url: str = "https://fal.cdn/test.jpg"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"images": [{"url": url, "width": 1024, "height": 1024}]}
    resp.raise_for_status = MagicMock()
    return resp


# --- is_enabled ---


def test_is_enabled_with_valid_key():
    assert nanobanana.is_enabled() is True


def test_is_enabled_false_when_key_missing(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    assert nanobanana.is_enabled() is False


def test_is_enabled_false_when_key_placeholder(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "changeme")
    assert nanobanana.is_enabled() is False


def test_is_enabled_false_when_key_missing_colon(monkeypatch):
    """FAL keys are <id>:<secret> — must contain a colon."""
    monkeypatch.setenv("FAL_KEY", "just-a-string-no-colon")
    assert nanobanana.is_enabled() is False


# --- generate_image ---


def test_generate_image_returns_url_on_success():
    with patch("app.services.nanobanana.requests.post", return_value=_ok_response("https://fal.cdn/x.jpg")):
        out = nanobanana.generate_image("CCTV warehouse with AI bounding boxes")
    assert out == "https://fal.cdn/x.jpg"


def test_generate_image_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    out = nanobanana.generate_image("anything")
    assert out is None


def test_generate_image_returns_none_on_network_error():
    import requests
    with patch("app.services.nanobanana.requests.post", side_effect=requests.RequestException("timeout")):
        out = nanobanana.generate_image("x")
    assert out is None


def test_generate_image_returns_none_on_4xx():
    import requests
    bad = MagicMock()
    bad.raise_for_status.side_effect = requests.HTTPError("400")
    with patch("app.services.nanobanana.requests.post", return_value=bad):
        out = nanobanana.generate_image("x")
    assert out is None


def test_generate_image_handles_single_image_response_shape():
    """Some FAL endpoints return {image: {url}} not {images: [{url}]}."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"image": {"url": "https://fal.cdn/single.jpg"}}
    resp.raise_for_status = MagicMock()
    with patch("app.services.nanobanana.requests.post", return_value=resp):
        out = nanobanana.generate_image("x")
    assert out == "https://fal.cdn/single.jpg"


def test_generate_image_returns_none_when_response_missing_url():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"unrelated": "shape"}
    resp.raise_for_status = MagicMock()
    with patch("app.services.nanobanana.requests.post", return_value=resp):
        out = nanobanana.generate_image("x")
    assert out is None


# --- download_image ---


def test_download_image_writes_file(tmp_path):
    resp = MagicMock()
    resp.iter_content = lambda chunk_size: [b"\xff\xd8\xff\xe0fakejpg"]
    resp.raise_for_status = MagicMock()
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    target = tmp_path / "img.jpg"
    with patch("app.services.nanobanana.requests.get", return_value=resp):
        out = nanobanana.download_image("https://fal.cdn/x.jpg", str(target))
    assert out == str(target)
    assert target.read_bytes().startswith(b"\xff\xd8")


def test_download_image_returns_none_on_failure(tmp_path):
    import requests
    target = tmp_path / "img.jpg"
    with patch("app.services.nanobanana.requests.get", side_effect=requests.RequestException("boom")):
        out = nanobanana.download_image("https://fal.cdn/x.jpg", str(target))
    assert out is None
    assert not target.exists()
