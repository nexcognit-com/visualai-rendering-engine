# Contract: Layer 2.5 Image Router (Provider-Agnostic Image Generation)

**Date**: 2026-05-03
**Owner**: Layer 2 (`../visualai-orchestration/`) — package `app/router/`
**Touches**: `app/router/__init__.py`, `app/router/image.py`, `app/router/_provider_nanobanana.py`
**Consumed by**: `app/routes/product_shoots.py`

This contract defines Layer 2.5's first public surface: image generation. It abstracts the upstream provider (NanoBanana Pro for Step 3) behind a stable Python interface so swapping to OpenAI `gpt-image-1` or Google Imagen 4 is a one-file addition + env-var change.

The Layer 2.5 package boundary documents future scaling: when image generation latency or throughput exceeds Layer 2's tolerance, the package can split into a separate microservice without changing the public contract.

---

## 1. Public interface

```python
# app/router/__init__.py
"""Layer 2.5 — Dynamic Model Router.

Provider-agnostic dispatch for AI generation. Step 3 ships image generation only;
video generation (router/video.py for Veo / Kling / Luma) is reserved for a follow-up.
"""
from .image import generate_studio_photos

__all__ = ["generate_studio_photos"]
```

```python
# app/router/image.py
async def generate_studio_photos(
    *,
    input_image_url: str,
    description: str = "",
    count: int = 6,
    timeout_seconds: int = 90,
    output_dir: str,
) -> list[str]:
    """Generate `count` studio-quality product photos from a single source image.

    Args:
        input_image_url: URL the upstream provider can fetch (typically a Layer 2
            pre-signed URL pointing into storage/uploads/<tenant>/).
        description: Optional context string. Passed verbatim to the provider's prompt.
        count: Target image count. Step 3 only supports count=6 (NanoBanana Pro's
            edit/multi endpoint default). Other counts raise ValueError.
        timeout_seconds: Total time budget. Provider call + slicing must finish within this.
        output_dir: Directory to write the resulting JPEGs. Created if missing.

    Returns:
        List of 6 absolute local file paths, in the order returned by the provider.

    Raises:
        ValueError: count != 6 (Step-3 limitation)
        ProviderTimeout: upstream exceeded timeout_seconds
        ProviderError: upstream returned 5xx or invalid response
        ProviderInvalidResponse: response shape doesn't match expected (not 1 sheet
            and not 6+ individual images)
    """
```

---

## 2. Internal flow

```
generate_studio_photos
  ├── Lookup provider from LAYER25_IMAGE_PROVIDER env-var
  │     └── default: "nanobanana"
  ├── Call provider adapter:
  │     await provider.generate(input_image_url, description, count, timeout)
  │     → returns list[bytes] (6 image payloads) OR 1-element list (contact sheet)
  ├── Detect contact sheet (R5):
  │     if len(payloads) == 1:
  │         img = Image.open(BytesIO(payloads[0]))
  │         w, h = img.size
  │         if w / h ≈ 3 / 2 AND w > 2000:  # heuristic
  │             payloads = slice_contact_sheet(img, count=6)
  │         else:
  │             raise ProviderInvalidResponse("single image but not sheet shape")
  │     elif len(payloads) < count:
  │         raise ProviderInvalidResponse(f"got {len(payloads)} images, need {count}")
  ├── Write each payload as JPEG into output_dir/shot-<N>.jpg
  └── Return [output_dir/shot-1.jpg, ..., output_dir/shot-6.jpg]
```

---

## 3. Provider adapter interface

Every provider adapter under `app/router/_provider_<name>.py` MUST implement:

```python
# app/router/_provider_<name>.py
from typing import Protocol


class ImageProvider(Protocol):
    name: str  # e.g. "nanobanana"

    async def generate(
        self,
        input_image_url: str,
        description: str,
        count: int,
        timeout_seconds: int,
    ) -> list[bytes]:
        """Returns raw image bytes (JPEG/PNG/WebP).

        May return either:
        - `count` separate image payloads (preferred), OR
        - 1 contact-sheet payload (caller will slice)

        Raises ProviderTimeout, ProviderError, ProviderInvalidResponse.
        """
```

### 3.1 NanoBanana adapter (`_provider_nanobanana.py`)

Step-3 reference implementation:

```python
import httpx
import os

name = "nanobanana"

async def generate(
    input_image_url: str,
    description: str,
    count: int,
    timeout_seconds: int,
) -> list[bytes]:
    api_key = os.environ["LAYER25_NANOBANANA_API_KEY"]
    prompt = (
        f"6 professional studio product photographs of the item shown. "
        f"Different angles and lighting setups. {description}"
    )
    payload = {
        "image_urls": [input_image_url],
        "prompt": prompt,
        "num_images": count,
        "output_format": "jpeg",
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            r = await client.post(
                "https://fal.run/fal-ai/nano-banana-pro/edit/multi",
                headers={"Authorization": f"Key {api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as e:
            raise ProviderTimeout(f"nanobanana timeout after {timeout_seconds}s") from e
        if r.status_code >= 500:
            raise ProviderError(f"nanobanana 5xx: status={r.status_code}")
        r.raise_for_status()
        body = r.json()

    # Response shape A: {"images": [{"url": "..."}, {"url": "..."}, ...]}
    # Response shape B: {"image": {"url": "..."}}  (contact sheet)
    if "images" in body and isinstance(body["images"], list):
        urls = [img["url"] for img in body["images"]]
        return await _fetch_all(urls, timeout_seconds)
    if "image" in body and "url" in body["image"]:
        return await _fetch_all([body["image"]["url"]], timeout_seconds)
    raise ProviderInvalidResponse(f"unexpected response shape: keys={list(body.keys())}")


async def _fetch_all(urls: list[str], timeout: int) -> list[bytes]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        responses = await asyncio.gather(*[client.get(u) for u in urls])
    return [r.content for r in responses]
```

### 3.2 Future adapters (out of scope for Step 3)

`_provider_openai_gpt_image.py` and `_provider_imagen.py` are listed as future swaps in research.md R2. The Step-3 deliverable is the architectural seam; only the NanoBanana adapter ships in PR-B.

---

## 4. Error taxonomy

```python
# app/router/exceptions.py
class ProviderTimeout(Exception): ...
class ProviderError(Exception): ...
class ProviderInvalidResponse(Exception): ...
```

Translation to HTTP at the routes layer:

| Exception | HTTP status | error_code |
|---|---|---|
| `ProviderTimeout` | 504 | `provider_timeout` |
| `ProviderError` | 502 | `provider_error` |
| `ProviderInvalidResponse` | 502 | `provider_invalid_response` |

`provider_error` retries are NOT performed at this layer in Step 3 — Layer 2 routes layer surfaces the error directly. Step 4 may add a 1-retry policy in the adapter.

---

## 5. Contact-sheet slicing utility

```python
# app/router/_slicing.py
from PIL import Image
from io import BytesIO


def slice_3x2_contact_sheet(sheet_bytes: bytes) -> list[bytes]:
    """Slice a 3-column × 2-row contact sheet into 6 individual JPEGs.

    Args:
        sheet_bytes: raw image bytes of the sheet.

    Returns:
        6 raw JPEG payloads, in row-major order: [r0c0, r0c1, r0c2, r1c0, r1c1, r1c2].

    The caller is responsible for deciding whether the input IS a contact sheet;
    this function blindly slices.
    """
    img = Image.open(BytesIO(sheet_bytes))
    w, h = img.size
    cell_w, cell_h = w // 3, h // 2
    out: list[bytes] = []
    for row in range(2):
        for col in range(3):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            cell = img.crop(box)
            buf = BytesIO()
            cell.save(buf, "JPEG", quality=92)
            out.append(buf.getvalue())
    return out


def looks_like_contact_sheet(img_bytes: bytes) -> bool:
    """Heuristic: 3:2 aspect ratio AND > 2000px wide → likely a sheet."""
    img = Image.open(BytesIO(img_bytes))
    w, h = img.size
    if w < 2000:
        return False
    ratio = w / h
    return 1.4 < ratio < 1.6  # ~3:2 with some tolerance
```

---

## 6. Test contract

### 6.1 `tests/router/test_image.py` (Layer 2.5)

Required cases (all use `respx` for HTTP mocking + Pillow for image fixtures):

| Test ID | Scenario | Expected |
|---|---|---|
| IR-1 | NanoBanana mock returns 6 individual image URLs | 6 local files written; no slicing happens |
| IR-2 | NanoBanana mock returns 1 contact sheet (3000×2000) | Slicing yields 6 files; each ~1000×1000 |
| IR-3 | NanoBanana mock returns 1 image of non-sheet aspect (1024×1024) | `ProviderInvalidResponse` raised |
| IR-4 | NanoBanana mock returns 4 images | `ProviderInvalidResponse` raised |
| IR-5 | NanoBanana mock takes 95s with 90s budget | `ProviderTimeout` raised |
| IR-6 | NanoBanana mock returns 503 | `ProviderError` raised |
| IR-7 | `count != 6` argument | `ValueError` (caller misuse) |
| IR-8 | `description=""` (empty) | Prompt sent without trailing whitespace; 200 OK |
| IR-9 | `output_dir` doesn't exist | Created automatically; 6 files written |
| IR-10 | `LAYER25_IMAGE_PROVIDER=unknown` | `ValueError("unknown provider: unknown")` at lookup |
| IR-11 | Slicing preserves row-major order (check via fixture with embedded numbers) | shot-1..6 match positions |

### 6.2 Slicing-only tests (`tests/router/test_slicing.py`)

| Test ID | Scenario | Expected |
|---|---|---|
| SL-1 | `slice_3x2_contact_sheet(3000×2000 sheet)` | 6 cells, each 1000×1000 |
| SL-2 | `looks_like_contact_sheet(3000×2000)` | `True` |
| SL-3 | `looks_like_contact_sheet(1024×1024)` | `False` |
| SL-4 | `looks_like_contact_sheet(800×600)` | `False` (too small) |
| SL-5 | `looks_like_contact_sheet(2400×1500)` | `True` (3:2 with tolerance) |

---

## 7. Concurrency + thread-safety

`generate_studio_photos` is `async def`. Multiple in-flight calls are safe:
- `httpx.AsyncClient` instances are created per-call (no shared client → no connection-pool contention)
- Pillow `Image.open` is thread-safe for read; the slicing function operates on bytes only
- File writes use unique paths per generation (output_dir = `storage/tasks/<id>/`)

No global state. No locks. Each generation is independent.

---

## 8. Forward compatibility — when video generation lands

The package boundary already accommodates `app/router/video.py`:

```python
# app/router/__init__.py — future shape
from .image import generate_studio_photos
from .video import generate_video_clip  # Step 5+

__all__ = ["generate_studio_photos", "generate_video_clip"]
```

Same provider-adapter pattern (`_provider_veo.py`, `_provider_kling.py`, `_provider_luma.py`).
Same error taxonomy.
Same env-var-driven provider selection.

The contract is intentionally narrow in Step 3 (image only) — this constrains scope while reserving the architectural shape.
