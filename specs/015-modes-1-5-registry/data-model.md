# Data Model: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Date**: 2026-05-03
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

This document captures the **logical** entities introduced or extended by Step 3. Step 3 stays filesystem-backed (no new database); a Step 4 migration moves these entities to Neon Postgres. The shapes here are the source of truth for the Step-4 schema.

Layer 3 owns: Mode (registry), VideoParams.mode literal extension, the visuals.json sidecar shape extension.
Layer 2 owns: Product Shoot Generation (in-memory + filesystem), Pre-signed URL (HMAC issuance), Upload (canonical bytes).
Layer 1 owns: nothing persistent — all state lives in Layer 2 or Layer 3.

---

## E1. Mode (registry interface) — Layer 3

**Purpose**: Defines the contract every active mode in `app/services/modes/` exports. The registry IS the constitution Principle V mechanism.

**Type**: `typing.Protocol` (structural typing — no inheritance required).

**Module location**: `app/services/modes/_interface.py`

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | yes | Stable mode identifier matching `VideoParams.mode` literal. e.g. `"short"`, `"faceless"` |
| `default_aspect_ratio` | `VideoAspect` enum | yes | Vertical 9:16 for Mode 2 + Mode 5; reserved 16:9 for future Mode 3 |

**Methods** (all module-level functions, NOT instance methods — modes are stateless):

| Method | Signature | Description |
|---|---|---|
| `generate_script(params)` | `(VideoParams) -> str` | Mode-specific LLM prompt + invocation. Mode 2 uses hook-body-CTA; Mode 5 uses topic-driven faceless template |
| `generate_terms(params, video_script)` | `(VideoParams, str) -> list[str]` | Mode-specific search-term generation. Mode 2 returns product-centric terms (or extracts setting tag if hybrid); Mode 5 returns generic faceless terms |
| `select_visuals_strategy(params)` | `(VideoParams) -> Literal["auto","user_uploaded","hybrid"]` | Returns which visual sourcing strategy `material.py` should apply. Mode 5 always returns `"auto"`; Mode 2 returns `params.visuals_mode` (preserves wizard choice) |

**Validation rules**:
- `name` MUST equal one of the `VideoParams.mode` literal values
- A module without all three method exports MUST fail import (mypy/pyright catches at type-check time; runtime registry init validates via Protocol check)
- A module is registered IFF its mode produces a video render task. Mode 1 (product shoot) is **not** registered — its output isn't a video

**State transitions**: None. Modes are pure stateless modules; the only "state" is what `_REGISTRY` knows about, which is fixed at import time.

**Registry table** (`app/services/modes/__init__.py`):

| Mode literal | Module | Status | Notes |
|---|---|---|---|
| `"short"` | `app/services/modes/short.py` | registered | Mode 2 — Short Marketing Video (active since Step 1) |
| `"faceless"` | `app/services/modes/faceless.py` | registered | Mode 5 — Faceless Channel Automation (new in Step 3) |
| `"product_shoot"` | — | NOT registered | Mode 1 dispatches Layer 2 → Layer 2.5; never reaches Layer 3 |
| Mode 3 (`"long"`) | — | reserved | Step 4 |
| Mode 4 (`"avatar"`) | — | reserved | Step 4 |

---

## E2. VideoParams.mode (extended literal) — Layer 3

**Purpose**: The dispatch field that tells `task.py` which mode module to pick.

**File**: `app/models/schema.py`

**Pre-Step-3 shape** (from spec 013 + spec 014):
```python
mode: Literal["short", "faceless"] = "short"
```

**Step-3 shape**:
```python
mode: Literal["short", "faceless", "product_shoot"] = "short"
```

**Notes**:
- `"product_shoot"` is added for completeness so the literal covers all five-mode-set members that ever flow through the API. Layer 3 never receives a `VideoParams` with `mode="product_shoot"` — Mode 1 hits Layer 2's `/api/v1/product-shoots` endpoint, which uses a separate Pydantic model entirely. The literal is widened only so future schema-derived clients see all valid values.
- A render task with `mode="product_shoot"` is rejected at the Layer 3 controller boundary with `422 unsupported_mode_for_render` before it ever reaches `task.py`.

**Validation rules**:
- Default value preserves backwards compatibility (Mode 2 is current)
- `script_mode` field (added in spec 013) remains orthogonal — `mode` and `script_mode` compose freely

---

## E3. visuals.json sidecar (extended) — Layer 3 reads, Layer 2 writes

**Purpose**: Per-task contract Layer 2 writes alongside the video task before dispatching to Layer 3. Layer 3's `material.download_videos` reads it to know whether to fetch from pre-signed URLs (Mode 2 Auto + Hybrid) or from Pexels (Mode 5 only).

**File path** (Layer 3 perspective): `storage/tasks/<task_id>/visuals.json`

**Pre-Step-3 shape** (added in Step 2):
```json
{
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "mode": "short",
  "visuals_mode": "auto",
  "user_uploaded_paths": []
}
```

**Step-3 extension** — adds `pre_signed_clip_urls`:

```json
{
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "mode": "short",
  "visuals_mode": "auto",
  "user_uploaded_paths": [],
  "pre_signed_clip_urls": [
    "http://localhost:8088/_signed/a1b2c3d4e5f6.../demo-tenant-001/abc123.jpg?expires=1714867200",
    "http://localhost:8088/_signed/b2c3d4e5f6a1.../demo-tenant-001/def456.jpg?expires=1714867200"
  ]
}
```

**Field semantics**:

| Field | Type | When present | Description |
|---|---|---|---|
| `pre_signed_clip_urls` | `list[str] \| null` | Mode 2 Auto + Hybrid | URLs Layer 3 fetches via plain `requests.get`. Each URL HMAC-signed with 15-min TTL by Layer 2. `null` (or absent) means "fall back to direct Pexels" — only valid when `mode == "faceless"` |
| (existing) `user_uploaded_paths` | `list[str]` | Mode 2 user_uploaded + Hybrid | Local filesystem paths under `storage/uploads/<tenant_id>/`. Layer 3 reads these directly (Step 3 retains debt #6 — Layer 3 keeps a mounted view of Layer 2's uploads dir until Step 4) |

**Validation rules at Layer 3**:
- If `pre_signed_clip_urls` is present AND non-empty → fetch from URLs; do NOT call Pexels regardless of mode
- If `pre_signed_clip_urls` is `null` or absent AND `mode == "faceless"` → call Pexels (constitution Principle IV exception for Mode 5)
- If `pre_signed_clip_urls` is `null` or absent AND `mode != "faceless"` → fail with `material.error.no_visuals_source` (this should never happen — Layer 2 always writes URLs for non-faceless modes)

**Migration note for Mode 2 Auto path** (debt #3 burndown):
- Pre-Step-3: Layer 3's `material.py` called Pexels + Pixabay HTTP directly when `visuals_mode=="auto"` regardless of mode.
- Post-Step-3: Layer 2 calls Pexels + Pixabay (in its existing `app/services/stock_provider.py` — moves over from Layer 3) and writes the resulting URLs into `pre_signed_clip_urls`. Layer 3's `material.py` only sees URLs.
- Mode 2 hybrid path remains direct Pexels in Layer 3 as smaller residual debt #3 (Step 3.5 finishes the burn).

---

## E4. Product Shoot Generation — Layer 2 (in-memory + filesystem)

**Purpose**: A Mode 1 generation run. Lives entirely in Layer 2 (with optional Layer 2.5 routing). NEVER reaches Layer 3.

**Storage**: In-memory `dict[str, ProductShootGeneration]` keyed by `id`, plus filesystem at `storage/tasks/<id>/` for output images. Step 4 migrates to Neon `product_shoot_generations` table.

**Pydantic model** (Layer 2):

```python
class ProductShootGeneration(BaseModel):
    id: str                          # UUID4 hex
    tenant_id: str                   # from JWT
    user_id: str                     # from JWT
    source_image_url: str            # pre-signed URL of the user's uploaded product image
    description: str = ""            # optional context ("matte black water bottle", "rose gold earring")
    status: Literal["pending", "running", "complete", "failed"]
    output_image_urls: list[str] = []   # 6 pre-signed URLs once status == "complete"
    model_name: str = "nanobanana-pro"  # provider used (logged for audit)
    latency_ms: int | None = None       # filled when status moves to terminal
    cost_estimate_usd: float | None = None  # filled when status moves to terminal (log-only Step 3)
    error_code: str | None = None       # populated when status == "failed"
    error_message: str | None = None
    created_at: datetime                 # UTC, ISO-8601
    completed_at: datetime | None = None
```

**Field validation**:

| Field | Rule | On violation |
|---|---|---|
| `source_image_url` | MUST be a Layer 2 pre-signed URL pointing into `storage/uploads/<tenant_id>/` (matches the user's tenant) | 403 cross-tenant if pattern mismatches |
| `description` | Max 500 chars; blank allowed | 422 if too long |
| `output_image_urls` | MUST contain exactly 6 entries when `status == "complete"`; empty otherwise | Layer 2.5 normalisation guarantees this |
| `cost_estimate_usd` | Step-3: log-only, no enforcement; Step-4 will gate on credit balance | n/a |

**State transitions**:

```
pending → running       (Layer 2.5 starts the upstream call)
running → complete      (Layer 2.5 returns 6 URLs; output_image_urls populated)
running → failed        (Layer 2.5 errors; error_code + error_message populated)
```

States are terminal once `complete` or `failed`. No retry mutation; client retries by creating a new generation.

**Error code taxonomy** (per FR-014, FR-028):

| `error_code` | Meaning |
|---|---|
| `provider_timeout` | NanoBanana didn't respond within 90s |
| `provider_error` | Upstream returned 5xx |
| `provider_invalid_response` | Couldn't parse 6 images from response |
| `source_image_unreachable` | Couldn't fetch the source pre-signed URL (expired, missing) |
| `source_image_too_large` | Source image > 10 MB |
| `source_image_invalid_format` | Source image not JPEG/PNG/WebP |
| `internal_error` | Catch-all for unexpected exceptions |

**Filesystem layout** (Layer 2):

```
storage/tasks/<id>/
├── shot-1.jpg
├── shot-2.jpg
├── shot-3.jpg
├── shot-4.jpg
├── shot-5.jpg
├── shot-6.jpg
└── (optional) raw-response.json    # for debugging; not exposed in API
```

Each `shot-N.jpg` is served via the same `/_signed/...` HMAC URL pattern as uploads (E5 below). The pre-signed URLs in `output_image_urls` point to these files.

---

## E5. Pre-signed URL — Layer 2

**Purpose**: HMAC-signed time-limited URL pattern for Layer 2 → Layer 3 asset handoff and for serving output images to Layer 1. Step-3 stand-in for what Step 4's CDN signed URLs will become.

**Format**:

```
http://<layer2-host>:8088/_signed/<sig>/<tenant_id>/<filename>?expires=<unix>
```

**Components**:

| Part | Type | Description |
|---|---|---|
| `<sig>` | hex string, 32 chars | Truncated `hmac_sha256(LAYER2_SIGNING_KEY, "{tenant_id}/{filename}\|{expires}")` |
| `<tenant_id>` | string | Tenant scope; must match the tenant_id in the JWT of whoever requested the URL |
| `<filename>` | string | UUID + extension under `storage/uploads/<tenant_id>/` OR under `storage/tasks/<task_id>/` |
| `expires` | unix timestamp | URL is rejected after this; query-string param |

**Issuance** (Layer 2, `app/auth/pre_signer.py`):

```python
def sign_url(tenant_id: str, filename: str, ttl_seconds: int = 900) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{tenant_id}/{filename}|{expires}"
    sig = hmac.new(
        os.environ["LAYER2_SIGNING_KEY"].encode(),
        payload.encode(),
        "sha256",
    ).hexdigest()[:32]
    base = os.environ.get("LAYER2_PUBLIC_BASE_URL", "http://localhost:8088")
    return f"{base}/_signed/{sig}/{tenant_id}/{filename}?expires={expires}"
```

**Verification** (Layer 2, `app/routes/pre_signed.py`):

| Check | Failure mode | HTTP status |
|---|---|---|
| `expires > now()` | URL expired | 410 `url_expired` |
| `hmac.compare_digest(sig, expected)` | Signature mismatch | 403 `url_invalid_signature` |
| `os.path.exists(target)` | File doesn't exist | 404 `url_target_missing` |
| Path normalises within allowed roots | Path traversal attempt | 403 `url_invalid_path` |

**Roots accepted**:
- `storage/uploads/<tenant_id>/<filename>` — user-uploaded assets
- `storage/tasks/<task_id>/<filename>` — Mode 1 generated outputs (here `<tenant_id>` in URL is the owning tenant; `<filename>` includes the task subpath e.g. `mode1-abc123/shot-1.jpg`, OR a separate URL convention is used — see contract)

**TTL**:
- Default 15 minutes (`ttl_seconds=900`)
- Matches Step 2 JWT TTL — operations can think of "credentials" as one unit

**Validation rules**:
- `LAYER2_SIGNING_KEY` MUST be set; placeholder `changeme` rejected at startup (production safety check, parallel to JWT signing key)
- `LAYER2_SIGNING_KEY` is distinct from `LAYER2_JWT_SIGNING_KEY` — JWT signing and URL signing are separate concerns; rotating one shouldn't require rotating the other

**State transitions**: None. URLs are stateless — they're valid until `expires`, then permanently invalid.

---

## E6. Upload (extended) — Layer 2

**Purpose**: User-uploaded asset (product image for Mode 1, product video clip / image for Mode 2 hybrid). Step-2 introduced the basic shape; Step 3 confirms it works for Mode 1's source images.

**Filesystem path**: `storage/uploads/<tenant_id>/<uuid>.<ext>`

**Existing fields** (no Step-3 changes):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Filename stem |
| `tenant_id` | string | From JWT |
| `user_id` | string | From JWT |
| `original_filename` | string | Logged for audit; not used in path |
| `content_type` | string | `image/jpeg`, `image/png`, `image/webp`, `video/mp4` |
| `byte_size` | int | Validated against per-type limits (10 MB for images, 100 MB for videos) |
| `created_at` | datetime | |

**Validation rules** (Step 3 confirms these are stable):
- Image: max 10 MB, MIME ∈ {`image/jpeg`, `image/png`, `image/webp`}
- Video: max 100 MB, MIME ∈ {`video/mp4`, `video/quicktime`}
- Mode 1's source image accepts only image MIMEs; video upload to product-shoot endpoint → 422

---

## Cross-entity relationships

```
VideoParams.mode (E2)
  ├── "short"      → registry pick → modes/short.py  (E1)
  ├── "faceless"   → registry pick → modes/faceless.py (E1)
  └── "product_shoot" → REJECTED at Layer 3 controller (422)

Layer 2 receives Mode 2 / Mode 5 request
  ├── writes visuals.json sidecar (E3) into Layer 3's task dir
  │     └── pre_signed_clip_urls: list[Pre-signed URL (E5)]
  └── dispatches to Layer 3

Layer 2 receives Mode 1 request (POST /api/v1/product-shoots)
  ├── creates Product Shoot Generation (E4)
  │     └── source_image_url: Pre-signed URL (E5) pointing to Upload (E6)
  ├── calls Layer 2.5 router (.image.generate_studio_photos)
  │     └── upstream NanoBanana Pro → 6 images
  ├── slices contact sheet if needed (Pillow)
  ├── writes 6 files to storage/tasks/<id>/
  └── populates output_image_urls: list[Pre-signed URL (E5)] back to Layer 1
```

---

## Storage migration path to Step 4

**Step 4 will introduce Neon Postgres**. Each in-memory entity above maps cleanly to a future table:

| Step-3 entity | Step-4 table |
|---|---|
| Mode (E1) | (no table — code-only registry, stays in Python) |
| VideoParams.mode (E2) | `generations.mode` column (already on the planned schema) |
| visuals.json sidecar (E3) | `generations.visuals_payload` JSONB column |
| Product Shoot Generation (E4) | `product_shoot_generations` table (1:1 mapping; UUID PK, FK to `tenants.id`) |
| Pre-signed URL (E5) | (still URL-shaped — generated dynamically; no table) |
| Upload (E6) | `assets` table (planned, owned by Layer 2/4) |

The shapes here ARE the Step-4 schema. Step-3 chose filesystem + in-memory because adding Neon now is out of scope; the entity validators are Pydantic models that will become SQLAlchemy / Neon table definitions with no field changes.
