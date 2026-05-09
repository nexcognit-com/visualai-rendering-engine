# Contract: L2 Brand Library API

**Owner**: Layer 2 (`visualai-orchestration/app/routes/brand_library.py`)
**Caller**: Layer 1 (`visualai-frontend/src/app/api/brand/...`) via the existing `layer2Fetch` proxy.
**Spec links**: spec.md FR-001 through FR-010 · data-model.md (the three tables).

## Auth

Every endpoint reads `tenant_id` and `user_id` from the JWT, exactly like the existing L2 routes (spec 014). No new auth surface. Demo bearer fallback works in dev contexts (`LAYER2_TRUST_LOCAL_UPSTREAM=true`).

## Endpoints

### Brand logos

```
POST /api/v1/brand/logos          — register an existing L3 upload as a saved logo
GET  /api/v1/brand/logos          — list this tenant's live logos
DELETE /api/v1/brand/logos/{id}   — soft-delete a logo (does not delete L3 file)
```

#### POST /api/v1/brand/logos

The flow is two-step from L1's perspective:

1. L1 calls the existing `POST /api/v1/uploads/image` (already proxied by L2 → L3). Carries `role="brand_logo"`. L3 returns the canonical upload response with `{ path, original_path, mime_type, source_width_px, source_height_px, content_hash, ... }`.
2. L1 calls THIS endpoint with the L3 response data plus a creator-supplied `label`. L2 inserts the `brand_logo` row.

Request body:

```json
{
  "label": "Primary logo",
  "image_path": "storage/uploads/<tenant>/<uuid>.cropped.jpg",
  "original_path": "storage/uploads/<tenant>/<uuid>.png",
  "mime_type": "image/png",
  "width_px": 1280,
  "height_px": 1280,
  "has_alpha": true,
  "content_hash": "sha256:..."
}
```

Response 201:

```json
{
  "id": "<uuid>",
  "tenant_id": "<from-jwt>",
  "user_id": "<from-jwt>",
  "label": "Primary logo",
  "image_path": "storage/uploads/<tenant>/<uuid>.cropped.jpg",
  "thumbnail_url": "<L3-static-base>/storage/uploads/<tenant>/<uuid>.cropped.jpg",
  "mime_type": "image/png",
  "width_px": 1280,
  "height_px": 1280,
  "has_alpha": true,
  "created_at": "2026-05-10T12:34:56Z"
}
```

The `thumbnail_url` is a server-rendered convenience: `${NEXT_PUBLIC_LAYER3_VIDEO_BASE}/${image_path}` so L1 can `<img src=...>` directly without manual concat.

Errors:
- 400 `bad_request` — label out of range, image_path empty, hex check failed.
- 401 `unauthorized` — missing/invalid JWT.

#### GET /api/v1/brand/logos

Response 200:

```json
{
  "logos": [
    { /* same shape as POST response */ },
    ...
  ]
}
```

Filtered to `tenant_id = <jwt.tenant_id>` AND `deleted_at IS NULL`. Sorted by `created_at DESC`.

#### DELETE /api/v1/brand/logos/{id}

Soft-delete: `UPDATE brand_logo SET deleted_at = ? WHERE id = ? AND tenant_id = ?`.

- 404 if no live row matches the id within the caller's tenant (this also covers cross-tenant deletion attempts — Constitution §III).
- 200 on success: `{ "ok": true, "id": "<uuid>" }`.
- L3 image file is NOT deleted. Eviction is a separate operator-side concern.

### Brand colors

```
POST /api/v1/brand/colors         — save a hex color
GET  /api/v1/brand/colors         — list this tenant's colors
DELETE /api/v1/brand/colors/{id}  — hard-delete
```

#### POST /api/v1/brand/colors

```json
{ "label": "Brand orange", "hex": "#FF6B35" }
```

L2 normalizes: strips a leading `#` if present, uppercases to `FF6B35`, validates `^[0-9A-F]{6}$`. Returns 400 `invalid_hex` if validation fails.

Response 201:

```json
{
  "id": "<uuid>",
  "tenant_id": "<from-jwt>",
  "label": "Brand orange",
  "hex": "FF6B35",
  "hex_with_hash": "#FF6B35",
  "created_at": "..."
}
```

#### GET /api/v1/brand/colors

Sorted by `created_at DESC`.

#### DELETE /api/v1/brand/colors/{id}

Hard-delete: `DELETE FROM brand_color WHERE id = ? AND tenant_id = ?`. 404 if no row matches.

### Brand voice (singleton)

```
GET /api/v1/brand/voice           — get current voice (200 with empty text if none)
PUT /api/v1/brand/voice           — upsert
```

#### GET /api/v1/brand/voice

```json
{
  "text": "We build calm, judgment-free fitness tools for people over 50",
  "updated_at": "2026-05-10T12:34:56Z"
}
```

If no row exists for the tenant, returns `{ "text": "", "updated_at": null }` — never 404. The empty-string contract simplifies L1 (no special "not yet saved" branch).

#### PUT /api/v1/brand/voice

```json
{ "text": "..." }  // 0..280 chars
```

UPSERT: `INSERT ... ON CONFLICT (tenant_id) DO UPDATE`. Empty string is the deletion form.

Response 200: same shape as GET, with the new `updated_at`.

Errors:
- 400 `text_too_long` if length > 280.

### Internal: resolve_saved_logo

Not a public endpoint — used internally by the render-dispatch path (spec 009 integration) when a wizard request body carries `saved_logo_id` instead of an inline upload. Surface:

```python
def resolve_saved_logo(tenant_id: str, logo_id: str) -> dict | None:
    # SELECT image_path, mime_type FROM brand_logo
    # WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL;
    # Returns None on cross-tenant access (silent — never 200 with another tenant's path).
```

The render-dispatch route (in spec 009) calls this; if it returns None, dispatch fails with `400 saved_logo_not_found`. If it returns the path, dispatch substitutes it into the request that goes to L3 as if the wizard had uploaded the file directly.

## Tenant isolation tests (SC-005)

For each endpoint, the contract tests cover:

1. Tenant A's JWT cannot read tenant B's logos / colors / voice.
2. Tenant A's JWT cannot delete tenant B's logos / colors.
3. Tenant A's JWT cannot resolve tenant B's saved-logo id (silent None, not an error that leaks the asset's existence).
