# Implementation Plan: Brand Library — tenant-scoped persistent brand assets

**Branch**: `020-brand-library` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-brand-library/spec.md`

## Summary

A tenant-scoped persistent repository for brand assets, surfaced as a `/brand` page in Layer 1. v1 stores three asset kinds (logos, colors, voice) and integrates with the per-render overlay flow (spec 009) so saved logos are one-click pickable from any Mode wizard. The backend split is deliberate:

- **Layer 1** (`visualai-frontend`) — owns the `/brand` page UI, the wizard-side saved-logo picker, and the API proxy routes.
- **Layer 2** (`visualai-orchestration`) — owns asset metadata persistence (logos, colors, voice) via a new SQLite-backed store. v1 uses SQLite because L2 has no DB today and a single-file persistent store is the lowest-friction option that survives restarts. Migration to Neon is a future concern noted in `research.md`.
- **Layer 3** (`MoneyPrinterTurbo`, this repo) — **near-zero changes**. Logo image bytes are persisted via the existing `/api/v1/uploads/image` endpoint that already tenant-scopes uploads. The single L3 change is in `app/services/llm.py` (an approved fork-surface per Constitution §II): when the script-generation request carries a non-empty `brand_voice_text` field, prepend it to the system prompt. Pure plumbing — no business logic, fork-surface compliant.
- **Layer 4** (Neon) — out of scope at v1. The L2 SQLite schema is shaped so that a future migration to Neon is mechanical.

## Technical Context

**Language/Version**: TypeScript (Next.js 16, L1) and Python 3.11/3.12 (FastAPI, L2). Layer 3 unchanged.
**Primary Dependencies**: L1 — Next.js, the existing `layer2-client.ts` proxy. L2 — FastAPI, plus a new dependency on Python stdlib `sqlite3` (no third-party DB driver). No new L1 npm packages.
**Storage**: L2 SQLite at `visualai-orchestration/storage/brand_library.sqlite3`. Schema in `data-model.md`. L3 disk for logo image bytes (existing `storage/uploads/<tenant>/<uuid>.<ext>` path, already tenant-scoped).
**Testing**: pytest at L2 (per project convention) for the new endpoints + persistence layer. Vitest at L1 for the new page + saved-logo picker integration. No L3 tests since L3 is untouched.
**Target Platform**: Same as today — local dev and the same GPU host for L3, plus L1+L2 on whatever runs them in production.
**Project Type**: Multi-layer web service. Same as the rest of the project — L1/L2/L3 each in its own repo.
**Performance Goals**: Brand page load ≤ 1s with 0–10 logos + 0–10 colors + 1 voice (SC-003). Saved-logo picker render ≤ 100ms after wizard reaches the overlay step.
**Constraints**: Constitution §III (tenant context propagation) — every L2 endpoint reads tenant from JWT and scopes queries by it. §I (Layer 3 rendering-only) — no L3 changes. §V (mode-aware contract) — no new mode, no changes to the existing five.
**Scale/Scope**: Small at v1 — assumes ≤ a few hundred tenants and ≤ ~10 logos / ~10 colors per tenant. SQLite handles this without strain. Scale concerns kick in once tenants exceed ~50,000 — that is the planned trigger for the Neon migration.

## Constitution Check

*Gate evaluated against `.specify/memory/constitution.md` v1.2.0.*

| Principle | Status | Note |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | One L3 change: a single append to the LLM system-prompt block in `app/services/llm.py`. This is plumbing (string concat from a request field), not business logic — no user/credit/billing/CRUD logic introduced. Logo bytes still flow through the existing `/api/v1/uploads/image` endpoint without behavioral change. |
| **II. Surgical Fork Discipline** | PASS | The single L3 file touched (`app/services/llm.py`) is one of the six approved fork-surfaces. No new files, no new top-level modules in L3. |
| **III. Multi-Tenant Context Propagation** | PASS | Every new L2 endpoint authenticates via the existing JWT middleware and scopes every query by `tenant_id`. SC-005 mandates a cross-tenant isolation test. |
| **IV. External Asset Acceptance Over Direct API Calls** | PASS | No external generation API is introduced. SQLite is local persistence; logo storage reuses L3 disk. No NanoBanana/Veo/etc. integration. |
| **V. Mode-Aware Rendering Contract** | PASS | No new mode. No changes to existing modes' registry entries. Spec 009 is the integration point and is itself unchanged by this spec. |

**Gates: PASS, no Complexity Tracking entries needed.**

## Project Structure

### Documentation (this feature)

```text
specs/020-brand-library/
├── spec.md                        # /speckit.specify output
├── plan.md                        # this file
├── research.md                    # Phase 0 — decisions: SQLite vs Neon, soft-delete, route choice
├── data-model.md                  # Phase 1 — entity shapes (BrandLogo, BrandColor, BrandVoice) + SQLite schema
├── quickstart.md                  # Phase 1 — manual smoke walkthroughs (P1 + P2 + P3)
├── contracts/
│   ├── l2-brand-library-api.md    # Phase 1 — L2 endpoints (CRUD on logos/colors/voice; saved-logo resolve)
│   └── l1-saved-logo-picker.md    # Phase 1 — wizard-side picker contract (consumes spec 009 overlay surface)
├── checklists/
│   └── requirements.md            # /speckit.specify validation checklist
└── tasks.md                       # /speckit.tasks output
```

### Source Code (across the three repos)

```text
# Layer 1 — visualai-frontend (PRIMARY surface area for this spec)
src/app/
├── brand/
│   └── page.tsx                   # NEW — /brand route, the Brand Library page
└── api/
    └── brand/
        ├── logos/
        │   ├── route.ts           # NEW — POST (upload+save), GET (list), DELETE (soft-delete)
        │   └── [id]/route.ts      # NEW — DELETE specific logo
        ├── colors/
        │   ├── route.ts           # NEW — POST/GET
        │   └── [id]/route.ts      # NEW — DELETE
        └── voice/
            └── route.ts           # NEW — GET / PUT (singleton per tenant)

src/components/
├── brand-library/
│   ├── logo-grid.tsx              # NEW — saved-logo card grid
│   ├── color-chip-grid.tsx        # NEW — saved-color chip grid
│   └── voice-editor.tsx           # NEW — brand voice textarea
└── sidebar.tsx                    # MODIFIED — sidebar already points at /brand;
                                   #   no behavioral change, just a sanity-check.

# Layer 2 — visualai-orchestration (NEW endpoints + persistence)
app/
├── routes/
│   └── brand_library.py           # NEW — /api/v1/brand/{logos,colors,voice}
├── services/
│   └── brand_store.py             # NEW — SQLite persistence layer (CRUD on the 3 tables)
└── storage/
    └── brand_library.sqlite3      # NEW — singleton DB file (gitignored; created on first L2 boot)

# Layer 3 — MoneyPrinterTurbo (this repo) — ONE FILE TOUCHED
app/services/
└── llm.py                        # MODIFIED — prepend `brand_voice_text` from request body to system prompt
                                  #   when non-empty (T034b). Constitution §II approved fork-surface.
# Logo bytes ride the existing /api/v1/uploads/image path with role="brand_logo" (no L3 code change for that)
```

**Structure Decision**: Multi-layer, with L1 owning UX + the API proxy routes, L2 owning persistence + tenant-scoped CRUD, and L3 untouched. SQLite at L2 is the v1 storage choice — see `research.md` for the alternatives (Neon, Postgres, JSON files).

## Complexity Tracking

> Constitution Check passed cleanly — no violations to justify, no entries.

## Phase 0 — Research (Outputs)

See [research.md](./research.md). Headlines:

- **Storage backend**: SQLite at L2. Rejected: Neon (requires Layer 4 commitment that the project hasn't made yet), JSON files (race conditions on multi-creator-per-tenant edits), Redis (in-memory; loses data on restart). SQLite gives ACID + persistence + zero new infra.
- **Logo bytes path**: reuse `/api/v1/uploads/image`. Rejected: a new dedicated `/api/v1/uploads/brand-logo` endpoint (would duplicate the existing image-validation pipeline including alpha-channel handling). Saving the image as `role="brand_logo"` in the existing endpoint is a one-line change to the existing accept-list. Wait — actually, looking at the current code, role is a free-text param, so no L3 change is needed at all; L1 just sets `role: "brand_logo"` in its multipart form post.
- **Soft-delete vs hard-delete**: soft-delete logos (matches spec 018 hybrid persistence pattern; lets in-flight renders complete cleanly), hard-delete colors (re-creatable, no in-flight risk).
- **Route name `/brand` not `/brand-library`**: the existing L1 sidebar already points at `/brand`. Going with the established UX label rather than introducing two names.
- **Brand voice as singleton per tenant** vs list of voices: singleton at v1 because product framing is "your brand has a voice", not "your brand has voices". Future spec can lift the singleton constraint without a schema migration.
- **Hex color storage form**: uppercase, no leading `#` (e.g. `FF6B35`). Rejected: storing with the `#` (saves a conversion step at display but introduces a parser ambiguity at validation). Stored canonically; rendered with `#` prefix at display.

## Phase 1 — Design Artifacts

- **[data-model.md](./data-model.md)** — entity shapes for `BrandLogo`, `BrandColor`, `BrandVoice`. SQLite schema with the 3 tables, indices for tenant lookup, and the soft-delete partial-unique-index pattern.
- **[contracts/l2-brand-library-api.md](./contracts/l2-brand-library-api.md)** — L2 CRUD endpoints for the three asset kinds, plus a `resolve_saved_logo` helper used by the render-dispatch path to translate a saved-logo identifier into the actual L3-fetchable image path.
- **[contracts/l1-saved-logo-picker.md](./contracts/l1-saved-logo-picker.md)** — contract between this spec and spec 009 (per-render overlays). Defines the picker's data shape, the "this asset was deleted" warning behavior, and the "no saved logos yet — go to /brand" empty state.
- **[quickstart.md](./quickstart.md)** — three smoke-test journeys mapping to P1 / P2 / P3.

### Agent context update

This spec adds new L1 routes, new L2 endpoints, and a new L2 SQLite store. It does NOT add a new Agent Mode or change the constitution's principles. The `update-agent-context.sh` step is a no-op for this feature — recorded here so `/speckit-analyze` does not flag it as missing.

## Re-evaluation (post-design)

All Constitution gates re-checked after Phase 1 design. No drift. Layer 3's single touched file (`app/services/llm.py`) is one of the six approved fork-surfaces and the change is pure plumbing (no business logic). The L2 SQLite addition does not create a Layer-4-class persistence concern because the data is operational (tenant brand assets, not credit ledger / billing / user identity — those still live in NexCognit / Neon per Constitution §I).

Plan locked.
