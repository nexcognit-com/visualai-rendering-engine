# Phase 0 Research: Brand Library

**Feature**: `020-brand-library` | **Date**: 2026-05-10

No `[NEEDS CLARIFICATION]` markers in the spec. Decisions below are the architectural choices made before plan was written; documented for the record so future readers understand why these instead of the alternatives.

## Decision 1 — Storage backend: SQLite at Layer 2

**Decision**: Persist brand metadata (logo registry, colors, voice) in a single SQLite database file at `visualai-orchestration/storage/brand_library.sqlite3`.

**Rationale**:
- L2 has no DB today (verified by grep — no SQLAlchemy / asyncpg / aiosqlite / psycopg in the codebase). Adding any persistence is therefore a new dimension to L2 regardless of choice.
- SQLite ships with the Python stdlib (`sqlite3`) — zero new dependencies.
- ACID at the file level — concurrent edits from two creators in the same tenant cannot corrupt the store. The concurrency model is fine for the v1 expected load (≤ a few hundred tenants, ≤ ~10 assets per tenant).
- Single-file persistence survives L2 restarts. The "stack restart loses brand library" failure mode is unacceptable.
- Mechanical migration to Neon when Layer 4 lands: the SQLite schema in `data-model.md` uses portable types and the same partial-unique-index pattern the Neon middleware uses (e.g., `WHERE deleted_at IS NULL`).

**Alternatives considered**:
- **Neon (Postgres) at Layer 4**: rejected for v1. Layer 4 is not yet committed to as a runtime dependency for VisualAI (only the NexCognit middleware uses Neon today). Wiring L2 → Neon for one feature would either (a) bring in spec 014's tenant-context infrastructure prematurely or (b) create a parallel L2-owned Neon project the project hasn't yet planned for. Defer to a Step-5 cross-spec migration.
- **JSON files on disk**: rejected. Multi-creator-per-tenant edits would race on flush. SQLite handles the locking for free.
- **Redis**: rejected. In-memory with optional persistence; loses data on restart unless AOF is enabled, and configuring AOF correctly is more operational complexity than SQLite. Also: Redis is documented in the constitution as "transient render-progress state... MUST NOT be treated as a source of truth," which is exactly what this would be doing.
- **Layer 3 SQLite**: rejected. Constitution §I explicitly forbids business-state persistence in L3. The brand library is product state, not render state.

## Decision 2 — Logo bytes ride the existing `/api/v1/uploads/image` endpoint

**Decision**: When the creator uploads a logo on the `/brand` page, L1 calls the existing L3 image-upload route via the L2 proxy. The response includes the persisted path, which L1 then sends to the new L2 brand-logo metadata endpoint along with a label.

**Rationale**:
- The existing `/api/v1/uploads/image` route already does: tenant-scoping, MIME validation, dimension checks, alpha-channel handling, dimension warnings ("low_resolution"), file-size cap, sha256 audit hash, eviction policy. Reimplementing any of this for "brand_logo" specifically would duplicate hundreds of lines.
- The route already accepts a free-text `role` param. Setting `role: "brand_logo"` requires zero L3 changes.
- The response shape (with `path`, `original_path`, `mime_type`, `width`, `height`, `content_hash`) is exactly what the brand-logo metadata row needs to carry.

**Alternatives considered**:
- **Dedicated `/api/v1/uploads/brand-logo` endpoint**: rejected. Constitution §I forbids new business logic in L3, and this would either duplicate the image-validation pipeline (worse) or just thin-wrap it (pointless).
- **L2-side image validation + L3 disk write**: rejected. Tenant-scoped disk writes are an L3 concern (storage layout); duplicating that to L2 would create a second source of truth for upload paths.

## Decision 3 — Soft-delete logos, hard-delete colors

**Decision**: Logo deletion sets `deleted_at = now()` on the metadata row but leaves the L3 image file in place. Color deletion removes the row entirely.

**Rationale**:
- **Logos**: in-flight renders may already reference a saved logo by id at the moment a creator clicks delete. If the metadata row is hard-deleted, the render-dispatch path's `resolve_saved_logo(id)` would return null and the render would fail. Soft-delete: existing renders complete; new wizard opens see the asset as "deleted, pick another." Matches spec 018 hybrid persistence pattern.
- **Colors**: stored as 6 hex characters, trivially re-creatable. No in-flight render references a color row by id (colors are inlined into the per-render overlay payload at dispatch time, not resolved later). Hard-delete is fine.
- **Brand voice**: singleton per tenant; "deletion" is just clearing the text. The row stays (tracks updated_at audit).

**Alternatives considered**:
- **Hard-delete logos**: rejected. Risks in-flight render failures.
- **Soft-delete colors**: rejected. Pointless — no consumer holds a reference past the dispatch boundary.

## Decision 4 — Route is `/brand`, not `/brand-library`

**Decision**: The L1 page lives at `/brand`. The original spec drafts said `/brand-library`; this was changed before plan writeup.

**Rationale**:
- The existing L1 sidebar (`src/components/sidebar.tsx`) already points at `/brand`. The page label is "Brand Library" (long form), the URL is `/brand` (short form). Same pattern as `/billing` (URL) labeled "Billing & Credits" (sidebar text) and `/assets` (URL) labeled "My Assets".
- Changing the URL would require updating the sidebar, which would split the spec's surface area unnecessarily.

**Alternatives considered**:
- **Update sidebar to `/brand-library`**: rejected. Diverges from the established short-URL convention.

## Decision 5 — Brand voice singleton vs list

**Decision**: One brand voice per tenant at v1. Schema-wise this is a `brand_voice (tenant_id PRIMARY KEY, ...)` row, not a list.

**Rationale**:
- Product framing: "your brand has a voice" is a singular statement. Multiple voices within one tenant doesn't have a strong use case at v1.
- Future expansion (e.g., "campaign-specific voice variants") can add a `brand_voice_variant` table referencing the singleton; doesn't require a schema migration of the singleton itself.

**Alternatives considered**:
- **List of named voices**: rejected at v1. Adds a wizard-side picker that adds friction to the typical case (most creators want one voice). Defer.

## Decision 6 — Hex color canonical form: uppercase, no `#` prefix

**Decision**: Colors are stored as exactly 6 uppercase hex characters: `FF6B35`. Display always prepends `#`.

**Rationale**:
- Avoids dual-form ambiguity at validation time (no need to handle both `#FF6B35` and `FF6B35` as valid inputs).
- Uppercase is the more conventional canonical form (per CSS Colors Level 4 §4.1).
- Storing 6 chars instead of 7 saves a (trivial) byte per row but more importantly makes the schema constraint `CHECK (length(hex) = 6 AND hex GLOB '[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]')` precise.
- Display layer's `#` prefix is universal across HTML, MoviePy color args, and ffmpeg `lavfi color` filter.

**Alternatives considered**:
- **Store with `#` prefix**: rejected — see above on validation ambiguity.
- **Lowercase**: rejected — CSS spec prefers uppercase canonical form.
- **8-char ARGB (alpha-included)**: rejected at v1. Per-overlay opacity is already a separate field on the overlay payload; baking alpha into the color-store form forces the wizard to either ignore one or merge them. Keep concerns split.

## Decision 7 — Visual design tokens come from `analytics.nexcognit.com`

**Decision**: The Brand Library page styling is extracted from the live `analytics.nexcognit.com` reference site. Specifically: dark background (~`#0A0A0A`), card surfaces (~`#161616`), accent (~`#FF6B35` orange), text muted (~`#888`), typography stack matching the reference site.

**Rationale**:
- Spec 001 (UI Style) is in Draft and unimplemented. Waiting for it would block this spec indefinitely.
- The reference site IS the design source of truth in practice. Extracting tokens from it is the same approach a designer would take.
- When spec 001 lands and tokens become formal, the implementation reconciles by mapping the as-built tokens to the spec's named tokens; should be a 30-min refactor.

**Alternatives considered**:
- **Define new tokens in this spec**: rejected. Per FR-011, tokens are spec 001's responsibility; this spec consumes them, doesn't define them.
- **Wait for spec 001**: rejected. Would block this spec indefinitely.

## Decision 8 — No tests for L3 in this spec

**Decision**: No new L3 tests. L3 is untouched.

**Rationale**: Constitution §Development Workflow says "New mode code requires at least one smoke test". This spec adds no new mode and no L3 code — that gate doesn't apply. L1 (Vitest) and L2 (pytest) tests cover the new code.

**Alternatives considered**:
- **Add an L3 smoke test for `role=brand_logo`**: rejected. The existing `role` parameter accepts any string today; "brand_logo" is just a value, not a code path. No new code to test.
