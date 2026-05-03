# Contract: Layer 2 Product Shoots API (Mode 1)

**Date**: 2026-05-03
**Owner**: Layer 2 (`../visualai-orchestration/`)
**Touches**: `app/routes/product_shoots.py` (NEW), `app/router/image.py` (NEW — Layer 2.5)
**Consumed by**: Layer 1 frontend `/api/product-shoot/route.ts`

This contract defines the synchronous HTTP endpoint Layer 1 hits to generate a 6-image product photoshoot. The endpoint is **synchronous** in Step 3 (client awaits ~30s response); Step 4+ may convert to async + webhook-completion if NanoBanana p99 latency creeps over frontend tolerance.

---

## 1. Endpoint summary

```
POST /api/v1/product-shoots
Authorization: Bearer <jwt>
Content-Type: application/json

→ 200 OK { id, status: "complete", output_image_urls: [6×string], ... }
→ 422 (validation)
→ 401 (jwt failures, per Step 2 contract)
→ 502 (provider errors)
→ 504 (provider timeout)
```

---

## 2. Request schema

```python
class ProductShootRequest(BaseModel):
    source_image_url: str        # pre-signed URL of user's uploaded product image
    description: str = ""        # optional context, max 500 chars
    # tenant_id + user_id injected post-parse by JWT middleware (do NOT include in client body)
```

**Validation rules** (Pydantic + custom validators):

| Field | Rule | Failure code |
|---|---|---|
| `source_image_url` | Must start with `http://` or `https://` | 422 `invalid_source_url` |
| `source_image_url` | Path matches `/_signed/<sig>/<tenant_id>/<filename>?expires=<unix>` AND `<tenant_id>` matches JWT claim | 403 `cross_tenant_source` |
| `source_image_url` | Verifies HMAC + expiry server-side via `pre_signer.verify(url)` | 403 `invalid_signature` / 410 `url_expired` |
| `description` | Length ≤ 500 | 422 `description_too_long` |

**JWT requirements**:
- Same JWT contract as `/api/v1/videos` (Step 2).
- `tenant_id` + `user_id` extracted from claims, attached to the `ProductShootGeneration` record.

---

## 3. Response schemas

### 3.1 200 OK (success)

```json
{
  "id": "ps_a1b2c3d4e5f6",
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "status": "complete",
  "source_image_url": "http://localhost:8088/_signed/.../demo-tenant-001/source.jpg?expires=1714867200",
  "description": "matte black water bottle on wooden surface",
  "output_image_urls": [
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-1.jpg?expires=1714867200",
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-2.jpg?expires=1714867200",
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-3.jpg?expires=1714867200",
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-4.jpg?expires=1714867200",
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-5.jpg?expires=1714867200",
    "http://localhost:8088/_signed/.../task/ps_a1b2c3d4e5f6/shot-6.jpg?expires=1714867200"
  ],
  "model_name": "nanobanana-pro",
  "latency_ms": 32450,
  "cost_estimate_usd": 0.24,
  "created_at": "2026-05-03T14:22:11Z",
  "completed_at": "2026-05-03T14:22:43Z"
}
```

**Guaranteed**:
- `output_image_urls.length == 6` exactly (Layer 2.5 normalises contact-sheet vs individual images).
- All 6 URLs share the same `expires=` timestamp (15-min TTL from response time).
- `id` prefix is `ps_` to distinguish from video task IDs.

### 3.2 4xx / 5xx error shapes

```json
// 422 example
{
  "error_code": "description_too_long",
  "detail": "description must be ≤ 500 characters",
  "field": "description"
}

// 502 example (provider error)
{
  "error_code": "provider_error",
  "detail": "NanoBanana returned status 503",
  "request_id": "req_xyz789"
}

// 504 example
{
  "error_code": "provider_timeout",
  "detail": "NanoBanana exceeded 90s timeout",
  "request_id": "req_xyz789"
}
```

| HTTP status | error_code values |
|---|---|
| 401 | `missing_jwt`, `invalid_jwt`, `expired_jwt` (per Step-2 JWT contract) |
| 403 | `cross_tenant_source`, `invalid_signature` |
| 410 | `url_expired` |
| 422 | `invalid_source_url`, `description_too_long`, `source_image_too_large`, `source_image_invalid_format` |
| 502 | `provider_error`, `provider_invalid_response` |
| 504 | `provider_timeout` |
| 500 | `internal_error` |

---

## 4. Server-side flow

```
POST /api/v1/product-shoots
  1. JWT middleware validates + injects tenant_id, user_id (Step 2 contract)
  2. Validate body (ProductShootRequest)
  3. Verify source_image_url HMAC + tenant scope
  4. Create ProductShootGeneration record (status="pending", in-memory dict)
  5. Update record → status="running"
  6. Call layer25_image_router.generate_studio_photos(
        input_image_url=source_image_url,
        description=description,
        count=6,
     )
     - Layer 2.5 calls NanoBanana via `_provider_nanobanana.generate(...)`
     - Slices contact sheet if returned (Pillow)
     - Saves 6 jpgs to storage/tasks/<id>/shot-1..6.jpg
     - Returns 6 local file paths
  7. Sign each path → 6 pre-signed URLs (15-min TTL)
  8. Update record → status="complete", output_image_urls populated, latency_ms + cost_estimate_usd filled
  9. Return 200 with the record
```

**Idempotency**: NOT idempotent in Step 3. Retrying a request creates a new generation. Step 4 introduces an `Idempotency-Key` header pattern.

**Concurrency**: A single tenant may have multiple in-flight Mode 1 generations. No queue-throttling in Step 3; Step 4 introduces credit-balance check + per-tenant rate limit.

---

## 5. Layer 2.5 image-router contract (consumed)

```python
# app/router/image.py
async def generate_studio_photos(
    *,
    input_image_url: str,
    description: str = "",
    count: int = 6,
    timeout_seconds: int = 90,
) -> list[str]:
    """Returns 6 local file paths under storage/tasks/<task_id>/.

    Provider-agnostic. Selects provider via LAYER25_IMAGE_PROVIDER env var (default: 'nanobanana').
    """
```

Implementation per [research.md R2 + R5](../research.md):
- Provider selection via env-var lookup
- NanoBanana adapter at `app/router/_provider_nanobanana.py` calls `fal.run/fal-ai/nano-banana-pro/edit/multi`
- Contact-sheet detection + slicing via Pillow

Detailed contract: [layer25-image-router.md](layer25-image-router.md).

---

## 6. Test contract

### 6.1 `tests/routes/test_product_shoots.py` (Layer 2)

Required cases:

| Test ID | Scenario | Expected |
|---|---|---|
| PS-1 | POST without `Authorization` | 401 `missing_jwt` |
| PS-2 | POST with valid JWT + valid source_image_url + empty description | 200; 6 URLs returned; `status=="complete"` |
| PS-3 | POST with description=500-char string | 200 |
| PS-4 | POST with description=501-char string | 422 `description_too_long` |
| PS-5 | POST with `source_image_url` belonging to different tenant | 403 `cross_tenant_source` |
| PS-6 | POST with expired pre-signed `source_image_url` | 410 `url_expired` |
| PS-7 | POST with malformed `source_image_url` (no /_signed/ pattern) | 422 `invalid_source_url` |
| PS-8 | NanoBanana mock returns 503 twice | 502 `provider_error` (after retry policy in adapter) |
| PS-9 | NanoBanana mock takes 95s (>90s timeout) | 504 `provider_timeout` |
| PS-10 | NanoBanana mock returns 1 contact-sheet image | 200 with 6 URLs (slicing happens) |
| PS-11 | NanoBanana mock returns 6 individual images | 200 with 6 URLs (no slicing) |
| PS-12 | NanoBanana mock returns 4 images (malformed) | 502 `provider_invalid_response` |
| PS-13 | All 6 output URLs verify HMAC for the requesting tenant | True |
| PS-14 | All 6 output URLs share the same `expires=` value | True |
| PS-15 | Logs include tenant_id + user_id + cost_estimate_usd | structured log assertion |

### 6.2 Layer-1 proxy tests (Vitest, in frontend repo)

| Test ID | Scenario | Expected |
|---|---|---|
| FE-PS-1 | `POST /api/product-shoot` with multipart upload | Layer 2 receives JSON with pre-signed `source_image_url` |
| FE-PS-2 | Layer 2 returns 504 | Frontend surfaces "Generation timed out — please try again" |
| FE-PS-3 | Layer 2 returns 422 `description_too_long` | Frontend highlights description field |

---

## 7. Observability

Per FR-029, every Mode 1 generation logs (Loguru `bind()`):

```python
logger.bind(
    generation_id="ps_a1b2c3d4e5f6",
    tenant_id="demo-tenant-001",
    user_id="demo-user-001",
    mode="product_shoot",
    provider="nanobanana",
    source="layer2/product_shoots",
).info("product_shoot.complete latency_ms={lat} cost_usd={cost}", lat=32450, cost=0.24)
```

Step-3 = log-only. Step-4 = aggregated per-tenant analytics + credit-balance check.

---

## 8. Environment variables

| Var | Default | Purpose |
|---|---|---|
| `LAYER25_IMAGE_PROVIDER` | `nanobanana` | Provider selector. `nanobanana` \| `openai_gpt_image` \| `imagen` (future) |
| `LAYER25_NANOBANANA_API_KEY` | (required, no default) | FAL.ai API key for NanoBanana Pro |
| `LAYER25_NANOBANANA_TIMEOUT_S` | `90` | Per-request timeout for the upstream provider call |
| `LAYER2_SIGNING_KEY` | (required) | HMAC key for pre-signed URL issuance + verification |
| `LAYER2_PUBLIC_BASE_URL` | `http://localhost:8088` | Base URL injected into pre-signed URLs |

Production-safety check at startup: if any required key is missing or `changeme`, Layer 2 refuses to start (parallel to Step 2's JWT signing-key check).
