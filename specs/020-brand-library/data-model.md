# Data Model: Brand Library

**Feature**: `020-brand-library` | **Date**: 2026-05-10

Three persisted entities, all owned by Layer 2 in a SQLite database file at `visualai-orchestration/storage/brand_library.sqlite3`. Logo image bytes themselves live on Layer 3 disk (existing `storage/uploads/<tenant>/<uuid>.<ext>` path); the `brand_logo` row carries a pointer.

## Entity: BrandLogo

A tenant-scoped saved logo. Multiple per tenant.

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `id` | TEXT (uuid) | PRIMARY KEY | Generated at insert. |
| `tenant_id` | TEXT | NOT NULL | From JWT (Constitution §III). |
| `user_id` | TEXT | NOT NULL | Creator who uploaded. |
| `label` | TEXT | NOT NULL, 1..100 chars | Creator-supplied. |
| `image_path` | TEXT | NOT NULL | Path on Layer 3 disk, returned by `/api/v1/uploads/image`. Relative to L3 root, e.g. `storage/uploads/<tenant>/<uuid>.cropped.jpg`. |
| `original_path` | TEXT | NULLABLE | Pre-crop original, when available. |
| `mime_type` | TEXT | NOT NULL | `image/png`, `image/jpeg`, etc. |
| `width_px` | INTEGER | NOT NULL | From the upload response. |
| `height_px` | INTEGER | NOT NULL | From the upload response. |
| `has_alpha` | INTEGER (0/1) | NOT NULL | True for transparent PNGs. Drives the "no-alpha warning" behavior in the wizard. |
| `content_hash` | TEXT | NOT NULL | sha256 from the upload response. Used for dedup hint at wizard time. |
| `created_at` | TEXT (ISO 8601) | NOT NULL | UTC, set on insert. |
| `deleted_at` | TEXT (ISO 8601) | NULLABLE | Soft-delete sentinel. Per Decision 3 in research.md, in-flight renders complete but new wizard opens hide the asset. |

**Indexes**:

```sql
CREATE TABLE brand_logo (
  id            TEXT PRIMARY KEY,
  tenant_id     TEXT NOT NULL,
  user_id       TEXT NOT NULL,
  label         TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 100),
  image_path    TEXT NOT NULL,
  original_path TEXT,
  mime_type     TEXT NOT NULL,
  width_px      INTEGER NOT NULL CHECK (width_px > 0),
  height_px     INTEGER NOT NULL CHECK (height_px > 0),
  has_alpha     INTEGER NOT NULL CHECK (has_alpha IN (0, 1)),
  content_hash  TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  deleted_at    TEXT
);
CREATE INDEX idx_brand_logo_tenant_live
  ON brand_logo (tenant_id, created_at DESC)
  WHERE deleted_at IS NULL;
CREATE INDEX idx_brand_logo_dedup
  ON brand_logo (tenant_id, content_hash)
  WHERE deleted_at IS NULL;
```

**Lifecycle**:

```
[wizard upload]
    │
    ▼
L1 → L2 → L3 /api/v1/uploads/image (role="brand_logo")
    │     L3 writes bytes to tenant-scoped disk; returns { path, ... }
    │
    ▼
L1 → L2 POST /api/v1/brand/logos { label, ...upload_response }
    │     L2 INSERT brand_logo
    │
    ▼
visible in /brand page card grid
    │
    ├─► picked in wizard → render dispatch references id
    │     L2 resolve_saved_logo(id) → image_path
    │     L3 receives a path it can fetch; render proceeds
    │
    └─► creator deletes → L2 UPDATE brand_logo SET deleted_at = NOW()
          L3 file is NOT deleted (soft-delete only)
```

## Entity: BrandColor

A tenant-scoped saved hex color. Multiple per tenant.

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `id` | TEXT (uuid) | PRIMARY KEY | Generated at insert. |
| `tenant_id` | TEXT | NOT NULL | From JWT. |
| `user_id` | TEXT | NOT NULL | Creator. |
| `label` | TEXT | NOT NULL, 1..50 chars | E.g., "Brand orange". |
| `hex` | TEXT | NOT NULL, exactly 6 uppercase hex chars | Canonical form per Decision 6. |
| `created_at` | TEXT (ISO 8601) | NOT NULL | UTC. |

```sql
CREATE TABLE brand_color (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  user_id    TEXT NOT NULL,
  label      TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 50),
  hex        TEXT NOT NULL CHECK (
    length(hex) = 6
    AND hex GLOB '[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'
  ),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_brand_color_tenant
  ON brand_color (tenant_id, created_at DESC);
```

**Lifecycle**:

```
[wizard add]
    │
    ▼
L1 → L2 POST /api/v1/brand/colors { label, hex }
    │     L2 INSERT (canonical: uppercase, no #)
    │
    ▼
visible in /brand page chip grid
    │
    ├─► picked in wizard → hex inlined into per-render overlay payload
    │     (no resolve step needed; color is small, rendered directly)
    │
    └─► creator deletes → L2 DELETE row (hard-delete per Decision 3)
```

## Entity: BrandVoice

Tenant-scoped tagline / mission statement. **Singleton per tenant.**

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `tenant_id` | TEXT | PRIMARY KEY | One row per tenant. |
| `user_id` | TEXT | NOT NULL | Last editor. |
| `text` | TEXT | NOT NULL, 0..280 chars | Empty string == "no brand voice"; same as deletion. |
| `updated_at` | TEXT (ISO 8601) | NOT NULL | UTC. |

```sql
CREATE TABLE brand_voice (
  tenant_id  TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  text       TEXT NOT NULL CHECK (length(text) BETWEEN 0 AND 280),
  updated_at TEXT NOT NULL
);
```

**Lifecycle**:

```
[wizard edit]
    │
    ▼
L1 → L2 PUT /api/v1/brand/voice { text }
    │     L2 UPSERT (INSERT ... ON CONFLICT (tenant_id) DO UPDATE)
    │
    ▼
on every Auto-mode or Polish-mode script generation:
  L1 → L2 → L3 with brand_voice_text appended to LLM system prompt
  (when text is empty, no prompt change — byte-identical to today)
```

## Cross-entity invariants

- **Tenant scoping** (Constitution §III): every CRUD endpoint reads `tenant_id` from the JWT and scopes every query by it. No L2 endpoint exposes a way to read or mutate another tenant's data.
- **No L4 dependency**: the SQLite store is L2-local. When Layer 4 (Neon) lands, the same three tables migrate via a one-shot SQL dump; column types are deliberately Postgres-portable (TEXT, INTEGER, ISO-8601 timestamps).
- **Layer 3 oblivious**: L3 sees only the existing image-upload path. It has no concept of "BrandLogo" or "saved-logo id" — by the time a request reaches L3, it carries plain image paths.

## L2 boot behavior

On first L2 boot, `app/services/brand_store.py` checks for `storage/brand_library.sqlite3`. If absent, it creates the file and runs the schema above. Idempotent — subsequent boots reuse the existing file. Schema migrations are out of scope at v1 (single-version schema); when a v2 ships, a `schema_version` table will track applied migrations.
