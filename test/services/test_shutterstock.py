"""Spec 015 — Shutterstock image API client (OAuth + search + license)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import shutterstock


@pytest.fixture(autouse=True)
def _reset_token_cache_and_env(monkeypatch):
    """Each test starts with a clean cache + valid-looking creds."""
    shutterstock._token_cache["access_token"] = None
    shutterstock._token_cache["expires_at"] = 0.0
    monkeypatch.setenv("SHUTTERSTOCK_CONSUMER_KEY", "test-key")
    monkeypatch.setenv("SHUTTERSTOCK_CONSUMER_SECRET", "test-secret")
    monkeypatch.setenv("SHUTTERSTOCK_SUBSCRIPTION_ID", "test-sub-id")
    yield


def _mock_oauth_response(token: str = "fake-bearer-token"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": token, "expires_in": 3600, "token_type": "Bearer"}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_search_response(image_id: str = "12345", total: int = 1):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "total_count": total,
        "data": [
            {
                "id": image_id,
                "description": "test description",
                "assets": {
                    "preview": {"url": "https://thumb.shutterstock.com/x.jpg", "width": 450, "height": 800}
                },
            }
        ] * (1 if total > 0 else 0),
    }
    resp.raise_for_status = MagicMock()
    return resp


# --- is_enabled ---


def test_is_enabled_true_when_keys_set():
    assert shutterstock.is_enabled() is True


def test_is_enabled_false_when_key_missing(monkeypatch):
    monkeypatch.delenv("SHUTTERSTOCK_CONSUMER_KEY", raising=False)
    assert shutterstock.is_enabled() is False


def test_is_enabled_false_when_placeholder(monkeypatch):
    monkeypatch.setenv("SHUTTERSTOCK_CONSUMER_KEY", "changeme")
    assert shutterstock.is_enabled() is False


# --- _get_access_token ---


def test_get_access_token_mints_fresh_when_cache_empty():
    with patch("app.services.shutterstock.requests.post", return_value=_mock_oauth_response("token-1")) as p:
        token = shutterstock._get_access_token()
    assert token == "token-1"
    p.assert_called_once()


def test_get_access_token_returns_cached_when_fresh():
    """Second call within TTL hits cache, no second OAuth roundtrip."""
    with patch("app.services.shutterstock.requests.post", return_value=_mock_oauth_response("token-A")) as p:
        first = shutterstock._get_access_token()
        second = shutterstock._get_access_token()
    assert first == second == "token-A"
    p.assert_called_once()


def test_get_access_token_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SHUTTERSTOCK_CONSUMER_KEY", raising=False)
    assert shutterstock._get_access_token() is None


def test_get_access_token_returns_none_on_oauth_failure():
    import requests
    with patch(
        "app.services.shutterstock.requests.post",
        side_effect=requests.RequestException("boom"),
    ):
        assert shutterstock._get_access_token() is None


# --- search_images ---


def test_search_images_returns_typed_results():
    with patch("app.services.shutterstock.requests.post", return_value=_mock_oauth_response()), \
         patch("app.services.shutterstock.requests.get", return_value=_mock_search_response("img-99")):
        results = shutterstock.search_images("control room monitors", per_page=5)
    assert len(results) == 1
    assert results[0].id == "img-99"
    assert results[0].preview_url.startswith("https://")
    assert results[0].width == 450


def test_search_images_returns_empty_on_no_matches():
    """API returned 0 results — empty list, no exception."""
    with patch("app.services.shutterstock.requests.post", return_value=_mock_oauth_response()), \
         patch("app.services.shutterstock.requests.get", return_value=_mock_search_response(total=0)):
        results = shutterstock.search_images("super-niche-query")
    assert results == []


def test_search_images_returns_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SHUTTERSTOCK_CONSUMER_KEY", raising=False)
    assert shutterstock.search_images("anything") == []


def test_search_images_skips_malformed_items():
    """API returned an item with no 'assets' field — skip it, don't crash."""
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.return_value = {
        "total_count": 2,
        "data": [
            {"id": "good", "description": "ok", "assets": {"preview": {"url": "https://x", "width": 100, "height": 100}}},
            {"id": "bad", "description": "oops"},  # no assets
        ],
    }
    bad_resp.raise_for_status = MagicMock()
    with patch("app.services.shutterstock.requests.post", return_value=_mock_oauth_response()), \
         patch("app.services.shutterstock.requests.get", return_value=bad_resp):
        results = shutterstock.search_images("x")
    assert len(results) == 1
    assert results[0].id == "good"


# --- license_and_download_image ---


def test_license_and_download_writes_file(tmp_path):
    license_resp = MagicMock()
    license_resp.status_code = 200
    license_resp.json.return_value = {
        "data": [{"download": {"url": "https://download.shutterstock.com/full.jpg"}}]
    }
    license_resp.raise_for_status = MagicMock()

    download_resp = MagicMock()
    download_resp.iter_content = lambda chunk_size: [b"\xff\xd8\xff\xe0fakejpg"]
    download_resp.raise_for_status = MagicMock()
    download_resp.__enter__ = lambda self: self
    download_resp.__exit__ = lambda *a: None

    target = tmp_path / "img.jpg"
    with patch("app.services.shutterstock.requests.post") as mock_post:
        mock_post.side_effect = [_mock_oauth_response(), license_resp]
        with patch("app.services.shutterstock.requests.get", return_value=download_resp):
            out = shutterstock.license_and_download_image("12345", str(target))
    assert out == str(target)
    assert target.read_bytes().startswith(b"\xff\xd8")


def test_license_returns_none_when_no_subscription_id(monkeypatch, tmp_path):
    monkeypatch.delenv("SHUTTERSTOCK_SUBSCRIPTION_ID", raising=False)
    target = tmp_path / "x.jpg"
    out = shutterstock.license_and_download_image("12345", str(target))
    assert out is None
    assert not target.exists()


def test_license_returns_none_on_quota_exceeded():
    """Shutterstock returns 403 when monthly quota is hit; helper returns None."""
    import requests
    err_resp = MagicMock()
    err_resp.status_code = 403
    err_resp.raise_for_status.side_effect = requests.HTTPError("403 quota")

    with patch("app.services.shutterstock.requests.post") as mock_post:
        mock_post.side_effect = [_mock_oauth_response(), err_resp]
        out = shutterstock.license_and_download_image("12345", "/tmp/x.jpg")
    assert out is None
