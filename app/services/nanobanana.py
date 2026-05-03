"""NanoBanana image-generation client (spec 015 — Mode 5 hero-image supplement).

Generates synthetic images via FAL.ai's NanoBanana endpoint when stock
libraries don't have the niche tech/AI imagery the topic asks for
(e.g. CCTV with AI bounding boxes, AI dashboards, computer-vision overlays).

Used by :mod:`app.services.material._supplement_with_nanobanana_images`.

**Architectural debt note**: this calls FAL.ai directly from Layer 3,
which is a constitution Principle IV deviation. PR-B's Layer 2.5 image
router (``visualai-orchestration/app/router/image.py``) is the correct
home for this call. When PR-B lands, swap the body of
:func:`generate_image` to HTTP-call Layer 2 instead of FAL — the public
surface stays identical so :mod:`app.services.material` doesn't change.

Cost (NanoBanana via FAL): ~$0.04 per image. A typical Mode 5 supplement
of 5-8 images = $0.20-0.32 per video.

Disabled (returns ``None`` / ``[]``) when ``FAL_KEY`` is missing or
placeholder. Mode 5 falls back to stock-only in that case.
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from loguru import logger


_NANOBANANA_ENDPOINT = "https://fal.run/fal-ai/nano-banana"
_PLACEHOLDERS = ("", "changeme", "your-fal-key-here")


def is_enabled() -> bool:
    key = os.environ.get("FAL_KEY", "").strip()
    return key not in _PLACEHOLDERS and ":" in key  # FAL keys are <id>:<secret>


def generate_image(prompt: str, *, timeout_seconds: int = 90) -> Optional[str]:
    """Generate one image from the prompt; return its URL or ``None`` on failure.

    Failure modes that return ``None`` (graceful for caller's fallback):
    - FAL_KEY missing / malformed
    - Network error / timeout
    - Provider 4xx/5xx response
    - Response shape doesn't include an image URL
    """
    if not is_enabled():
        return None

    headers = {"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "num_images": 1, "output_format": "jpeg"}

    try:
        resp = requests.post(_NANOBANANA_ENDPOINT, headers=headers, json=payload, timeout=timeout_seconds)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"nanobanana generation failed for {prompt[:60]!r}: {exc}")
        return None

    body = resp.json()
    # NanoBanana shape: {"images": [{"url": "...", "width": ..., "height": ...}], ...}
    if isinstance(body, dict):
        images = body.get("images")
        if isinstance(images, list) and images:
            url = images[0].get("url")
            if isinstance(url, str) and url:
                logger.info(f"nanobanana generated image for {prompt[:60]!r} → {url[:80]}")
                return url
        # Some FAL endpoints return {"image": {"url": ...}}
        single = body.get("image")
        if isinstance(single, dict) and isinstance(single.get("url"), str):
            return str(single["url"])
    logger.warning(f"nanobanana response missing image url: keys={list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
    return None


def download_image(url: str, target_path: str) -> Optional[str]:
    """Stream an image URL to a local path. Returns the path or ``None``."""
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except (requests.RequestException, OSError) as exc:
        logger.warning(f"nanobanana image download failed for {url[:80]!r}: {exc}")
        return None
    return target_path


__all__ = ["is_enabled", "generate_image", "download_image"]
