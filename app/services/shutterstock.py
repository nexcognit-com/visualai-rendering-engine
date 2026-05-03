"""Shutterstock image API client (spec 015 — Mode 5 supplementary stock).

OAuth2 Client Credentials flow + image search + license-and-download.
Used by :mod:`app.services.material` to supplement Pixabay/Pexels video
results with Shutterstock images for tech/AI topics where stock video
inventory is thin (e.g. "control room monitors", "data center server racks").

Free tier: 500 image licenses per month. ``license_image()`` decrements
that quota — call it only after `search_images` confirms the image is a
match the caller actually wants to use.

Auth: Bearer token cached in-memory with safe TTL margin (refreshes at
50 minutes; Shutterstock tokens last 60 minutes).

Disabled (no-ops, returns []) when ``SHUTTERSTOCK_CONSUMER_KEY`` or
``SHUTTERSTOCK_CONSUMER_SECRET`` is missing or placeholder. Mode 5
falls back to Pixabay+Pexels alone in that case.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

import requests
from loguru import logger


_OAUTH_ENDPOINT = "https://api.shutterstock.com/v2/oauth/access_token"
_SEARCH_IMAGES_ENDPOINT = "https://api.shutterstock.com/v2/images/search"
_LICENSE_IMAGES_ENDPOINT = "https://api.shutterstock.com/v2/images/licenses"

# Token cache (module-level — process-wide)
_token_cache: dict[str, object] = {"access_token": None, "expires_at": 0.0}
# Refresh 10 min before actual expiry to avoid mid-call expiration races.
_TOKEN_REFRESH_MARGIN_S = 600

_PLACEHOLDERS = ("", "changeme", "your-key-here")


@dataclass(frozen=True)
class ShutterstockImage:
    """Single image hit from Shutterstock's search endpoint.

    ``preview_url`` is the watermarked thumbnail (free, public).
    To get the licensed full-resolution download URL, call
    :func:`license_image` with the ``id``.
    """

    id: str
    description: str
    preview_url: str
    width: int
    height: int


def _is_configured() -> bool:
    key = os.environ.get("SHUTTERSTOCK_CONSUMER_KEY", "").strip()
    secret = os.environ.get("SHUTTERSTOCK_CONSUMER_SECRET", "").strip()
    return key not in _PLACEHOLDERS and secret not in _PLACEHOLDERS


def _get_access_token() -> Optional[str]:
    """Return a valid bearer token, minting a fresh one if cached is missing
    or near expiry. Returns ``None`` when credentials aren't configured."""
    if not _is_configured():
        return None

    now = time.time()
    cached_token = _token_cache["access_token"]
    cached_expiry = float(_token_cache["expires_at"])  # type: ignore[arg-type]
    if cached_token and cached_expiry > now:
        return str(cached_token)

    key = os.environ["SHUTTERSTOCK_CONSUMER_KEY"]
    secret = os.environ["SHUTTERSTOCK_CONSUMER_SECRET"]
    try:
        resp = requests.post(
            _OAUTH_ENDPOINT,
            data={
                "client_id": key,
                "client_secret": secret,
                "grant_type": "client_credentials",
                "scope": "user.view licenses.create licenses.view",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"shutterstock OAuth failed: {exc}")
        return None

    body = resp.json()
    token = body.get("access_token")
    expires_in = int(body.get("expires_in", 3600))
    if not token:
        logger.warning(f"shutterstock OAuth returned no access_token: keys={list(body.keys())}")
        return None

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + max(60, expires_in - _TOKEN_REFRESH_MARGIN_S)
    logger.info(f"shutterstock token minted (expires_in={expires_in}s)")
    return token


def search_images(
    query: str,
    *,
    per_page: int = 10,
    image_type: str = "photo",
    orientation: str = "vertical",
) -> List[ShutterstockImage]:
    """Search Shutterstock's image library.

    Returns up to ``per_page`` :class:`ShutterstockImage` results. ``orientation``
    defaults to ``vertical`` to match Mode 5's 9:16 output aspect.

    Returns ``[]`` on any failure (auth missing, network error, no matches).
    """
    token = _get_access_token()
    if not token:
        return []

    try:
        resp = requests.get(
            _SEARCH_IMAGES_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "query": query,
                "per_page": per_page,
                "image_type": image_type,
                "orientation": orientation,
            },
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"shutterstock search failed for {query!r}: {exc}")
        return []

    body = resp.json()
    out: List[ShutterstockImage] = []
    for item in body.get("data", []):
        try:
            preview = item["assets"]["preview"]
            out.append(
                ShutterstockImage(
                    id=str(item["id"]),
                    description=str(item.get("description", "")),
                    preview_url=str(preview["url"]),
                    width=int(preview.get("width", 0)),
                    height=int(preview.get("height", 0)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    logger.info(f"shutterstock search '{query}' → {len(out)} hits (total={body.get('total_count', 0)})")
    return out


def license_and_download_image(image_id: str, target_path: str) -> Optional[str]:
    """License an image (counts against monthly quota) and download the
    full-resolution JPEG to ``target_path``.

    Returns the absolute local path on success, or ``None`` on any failure
    (including monthly-quota exceeded — Shutterstock returns 403 when the
    free 500/mo limit is hit).
    """
    token = _get_access_token()
    if not token:
        return None

    subscription_id = os.environ.get("SHUTTERSTOCK_SUBSCRIPTION_ID", "").strip()
    if not subscription_id:
        logger.warning("SHUTTERSTOCK_SUBSCRIPTION_ID not set; cannot license image")
        return None

    payload = {
        "images": [
            {
                "image_id": str(image_id),
                "subscription_id": subscription_id,
                "size": "huge",  # licensed JPEG; falls back automatically if not available
            }
        ]
    }
    try:
        resp = requests.post(
            _LICENSE_IMAGES_ENDPOINT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"shutterstock license failed for image {image_id}: {exc}")
        return None

    body = resp.json()
    licenses = body.get("data", [])
    if not licenses:
        logger.warning(f"shutterstock license returned no data for image {image_id}")
        return None

    download_url = licenses[0].get("download", {}).get("url")
    if not download_url:
        logger.warning(f"shutterstock license response missing download.url for image {image_id}")
        return None

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except (requests.RequestException, OSError) as exc:
        logger.warning(f"shutterstock image download failed for {image_id}: {exc}")
        return None

    logger.info(f"shutterstock licensed + downloaded image {image_id} → {target_path}")
    return target_path


def is_enabled() -> bool:
    """Quick check used by callers to skip the supplement path entirely
    when Shutterstock isn't configured."""
    return _is_configured()


__all__ = [
    "ShutterstockImage",
    "search_images",
    "license_and_download_image",
    "is_enabled",
]
