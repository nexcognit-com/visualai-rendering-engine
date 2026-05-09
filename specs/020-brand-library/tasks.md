---
description: "Task list for 020-brand-library"
---

# Tasks: Brand Library — tenant-scoped persistent brand assets

**Input**: Design documents from `/specs/020-brand-library/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/{l2-brand-library-api.md, l1-saved-logo-picker.md}, quickstart.md (all complete)

**Tests**: Test tasks ARE included. L2 gets pytest coverage for the new endpoints + persistence (SC-005 enforces tenant isolation; that's contract-test territory). L1 gets Vitest coverage for the page + picker.

**Organization**: Tasks are grouped by user story per spec.md priority. Setup phase covers the SQLite scaffolding (one-time per-repo), Foundational covers the kit-style helpers needed across all stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (per spec.md user stories)
- File paths are exact and match the plan.md project structure

## Path Conventions

Three repos:
- L1 = `/root/dev/visualai/visualai-frontend/`
- L2 = `/root/dev/visualai/visualai-orchestration/`
- L3 = `/root/dev/visualai/MoneyPrinterTurbo/` — **NOT TOUCHED** by this spec

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] L2: add `storage/` to `visualai-orchestration/.gitignore` (excluding any tracked exemplars). The new `brand_library.sqlite3` lands there.
- [ ] T002 [P] L1: confirm `next.config.ts` allows JSON imports if not already enabled (we don't import JSON, but `nexcognit.config.json` from spec 008 sets the precedent — sanity check).
- [ ] T003 L2: scaffold `app/services/brand_store.py` skeleton — connection helper + `init_schema()` + module-level lazy connection. No CRUD yet (later tasks fill that in).

**Checkpoint**: setup verified, no functional code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

These BLOCK every user story phase. Cannot start US1/US2/US3 until done.

- [ ] T004 L2: `app/services/brand_store.py` — implement `init_schema()` per data-model.md. Creates 3 tables (`brand_logo`, `brand_color`, `brand_voice`) + 3 indexes. Idempotent (CREATE IF NOT EXISTS). Run on L2 startup via `app/main.py` lifespan hook.
- [ ] T005 L2: `app/services/brand_store.py` — connection management. Use `sqlite3` stdlib with `check_same_thread=False` and a per-request lock OR a thread-local connection pool. Document choice.
- [ ] T006 [P] L2: write `tests/test_brand_store_init.py` — verifies `init_schema()` is idempotent (run 2x against an empty file, both succeed) and creates the expected tables/columns/indexes via `PRAGMA table_info`.
- [ ] T007 [P] L1: extend `src/lib/layer2-client.ts` if needed (probably no change — existing `layer2Fetch` proxies any path). Confirm with a one-line grep.
- [ ] T008 [P] L1: add the `Briefcase` icon import is correct in `src/components/sidebar.tsx` and the `/brand` route entry already exists. (Spot-check; no code change expected.)

**Checkpoint**: storage layer ready, L1 plumbing confirmed. User stories can begin.

---

## Phase 3: User Story 1 — Save a logo, reuse across modes (Priority: P1) 🎯 MVP

**Goal**: a creator can save a logo on `/brand` and pick it from any Mode wizard's overlay step.

**Independent Test**: per quickstart.md Journey A.

### Tests for User Story 1

- [ ] T009 [new] [P] [US1] L2: `tests/test_brand_logo_endpoints.py` — pytest covering POST/GET/DELETE on `/api/v1/brand/logos`:
  - happy path: POST then GET returns the new row
  - tenant isolation: tenant B cannot read or delete tenant A's logo (SC-005)
  - soft-delete: DELETE marks `deleted_at` but the row stays; second GET hides it
  - invalid label: empty / >100 chars rejected with 400
- [ ] T010 [new] [P] [US1] L1: `tests/brand-library-page.test.tsx` (Vitest) — renders the Brand Library page, mocks `GET /api/brand/logos` with empty + non-empty responses, asserts the empty-state vs grid-state UX.
- [ ] T011 [new] [P] [US1] L1: `tests/saved-logo-picker.test.tsx` (Vitest) — renders the picker with mocked logos, asserts onPick fires with the logo id, asserts the deleted-mid-wizard banner appears when `selectedLogoId` is no longer in the list.

### Implementation for User Story 1

- [ ] T012 [new] [US1] L2: `app/routes/brand_library.py` — register the route module on the FastAPI app. POST/GET/DELETE on `/api/v1/brand/logos` per `contracts/l2-brand-library-api.md`. Tenant from JWT, scoped queries via `brand_store`.
- [ ] T013 [new] [US1] L2: in `brand_store.py`, implement: `insert_logo(tenant_id, user_id, label, image_path, ...)`, `list_logos(tenant_id)`, `soft_delete_logo(tenant_id, logo_id)`, `resolve_saved_logo(tenant_id, logo_id)`. All take `tenant_id` to enforce isolation at the SQL level.
- [ ] T014 [new] [P] [US1] L1: `src/app/api/brand/logos/route.ts` — POST/GET handlers proxy to L2.
- [ ] T015 [new] [P] [US1] L1: `src/app/api/brand/logos/[id]/route.ts` — DELETE handler proxies to L2.
- [ ] T016 [new] [US1] L1: `src/app/brand/page.tsx` — the Brand Library page. Two-step upload flow: (a) call existing `/api/v1/uploads/image` with `role: brand_logo`, (b) call new `/api/brand/logos` to register. Card grid, empty state, delete affordance, label input.
- [ ] T017 [new] [P] [US1] L1: `src/components/brand-library/logo-grid.tsx` — pure card-grid component. Card shows thumbnail + label + timestamp + delete button.
- [ ] T018 [new] [P] [US1] L1: `src/components/brand-library/saved-logo-picker.tsx` — wizard-side picker per `contracts/l1-saved-logo-picker.md`. Includes empty state and deleted-mid-wizard banner.
- [ ] T019 [new] [US1] [blocked-on-spec-009] L1: integrate `<SavedLogoPicker>` into Mode 2's wizard at the overlay step. **Cannot complete until spec 009 ships its overlay step** — the picker has no host until then. The component itself (T018) is unblocked and shippable; T019 is the wire-up only.
- [ ] T020 [new] [US1] L1+L2: extend the render-dispatch flow to recognise `saved_logo_id` in the request body. L1 `/api/generate` proxies through; L2 calls `resolve_saved_logo` and substitutes the actual `image_path` into the request that goes to L3. Returns 400 `saved_logo_not_found` for unknown / cross-tenant ids.

**Checkpoint**: User Story 1 works end-to-end. Save → see in /brand grid → pick in Mode 2 wizard → render carries the logo.

---

## Phase 4: User Story 2 — Save a brand color (Priority: P2)

**Goal**: a creator can save a hex color and pick it from any rectangle-overlay color picker.

**Independent Test**: per quickstart.md Journey B.

### Tests for User Story 2

- [ ] T021 [new] [P] [US2] L2: `tests/test_brand_color_endpoints.py`:
  - happy path POST/GET/DELETE
  - tenant isolation
  - hex validation: rejects `#XYZ123`, `red`, `rgb(...)`, accepts `#FF6B35` and `ff6b35` (normalizes to uppercase no-`#`)

### Implementation for User Story 2

- [ ] T022 [new] [US2] L2: extend `brand_library.py` route module with POST/GET/DELETE `/api/v1/brand/colors`.
- [ ] T023 [new] [US2] L2: in `brand_store.py`, implement `insert_color`, `list_colors`, `delete_color` (hard-delete per Decision 3).
- [ ] T024 [new] [P] [US2] L1: `src/app/api/brand/colors/route.ts` + `src/app/api/brand/colors/[id]/route.ts` proxies.
- [ ] T025 [new] [P] [US2] L1: `src/components/brand-library/color-chip-grid.tsx` — chip grid with add-color form (label + hex input).
- [ ] T026 [new] [US2] L1: extend `src/app/brand/page.tsx` to mount the color-chip-grid below the logo-grid.
- [ ] T027 [new] [US2] [blocked-on-spec-009] L1: extend the wizard's color picker at the rectangle-overlay step to surface saved colors as labeled chips. **Cannot complete until spec 009 ships its rectangle-overlay step** — same blocker pattern as T019. The standalone `color-chip-grid.tsx` (T025) is unblocked and shippable.

**Checkpoint**: User Story 2 works end-to-end.

---

## Phase 5: User Story 3 — Brand voice as LLM context (Priority: P3)

**Goal**: a saved brand voice tagline is injected into LLM system prompts for Auto/Polish modes.

**Independent Test**: per quickstart.md Journey C.

### Tests for User Story 3

- [ ] T028 [new] [P] [US3] L2: `tests/test_brand_voice_endpoint.py`:
  - GET on a tenant with no row returns `{ text: "", updated_at: null }` (not 404)
  - PUT upserts; subsequent GET returns the new text
  - text > 280 chars rejected with 400
  - tenant isolation

### Implementation for User Story 3

- [ ] T029 [new] [US3] L2: extend `brand_library.py` route module with GET/PUT `/api/v1/brand/voice`.
- [ ] T030 [new] [US3] L2: in `brand_store.py`, implement `get_voice(tenant_id)` (returns empty-string default if no row) and `upsert_voice(tenant_id, user_id, text)`.
- [ ] T031 [new] [P] [US3] L1: `src/app/api/brand/voice/route.ts` proxy.
- [ ] T032 [new] [P] [US3] L1: `src/components/brand-library/voice-editor.tsx` — textarea with 280-char counter, save button, debounced autosave optional.
- [ ] T033 [new] [US3] L1: extend `src/app/brand/page.tsx` to mount the voice-editor.
- [ ] T034 [new] [US3] L2: in the script-generation forwarding path (`visualai-orchestration/app/routes/scripts.py` or wherever the LLM-bearing routes live), fetch the brand voice for the tenant and **attach it to the request body forwarded to L3** as a new `brand_voice_text` field. When empty: omit the field — byte-identical to today's body (FR-010 / SC-006 L2 side).
- [ ] T034b [new] [US3] L3 (`MoneyPrinterTurbo/app/services/llm.py`): when the script-generation request carries a non-empty `brand_voice_text`, prepend it to the system-prompt block that drives `generate_script` / `generate_marketing_script` / `generate_long_form_script`. When the field is absent or empty, the prompt is byte-identical to today (FR-010 / SC-006 L3 side). **Constitution §I OK**: this is plumbing (string append to an existing prompt template), not business logic. Touches the `app/services/llm.py` fork-surface (constitution §II).

**Checkpoint**: User Story 3 works end-to-end. Brand voice appears in LLM prompts only when saved. Verified by inspecting the L3 LLM dispatch logs in dev mode (T034b's append is observable in the system-prompt block).

---

## Phase 6: Polish & Cross-Cutting

- [ ] T035 L1 + L2 styling pass: tokens extracted from `analytics.nexcognit.com` per Decision 7. Apply to the Brand Library page and the wizard pickers. Document the as-built tokens in `plan.md` under "post-implementation notes" so spec 001 can reconcile later.
- [ ] T036 [P] L2: pytest suite passes. The new tests under `visualai-orchestration/tests/test_brand_*.py` all green.
- [ ] T037 [P] L1: Vitest suite passes. The new tests in `visualai-frontend/tests/brand-library-*.test.tsx` all green.
- [ ] T038 [P] Update L1's `.env.local` (no new vars expected, but verify) and L2's `.env` (also no new vars expected — SQLite is filesystem-based).
- [ ] T039 Smoke-test all three quickstart journeys (A, B, C) against a local L1+L2+L3 stack. Capture pass/fail per pass criterion.
- [ ] T040 Open the L1 PR (`feat(020): brand library page + saved-logo picker`) targeting the L1 integration branch, and the L2 PR (`feat(020): brand library API + SQLite store`) targeting the L2 main. PR base notes per the spec 008 / 019 pattern.

---

## Dependencies & Story Order

```
T001-T003 (setup)  ──┐
                     ▼
T004-T008 (foundational)  ──► US1 → US2 → US3
                                │     │     │
                                ▼     ▼     ▼
                          T020 (US1 wire)
                          T027 (US2 wire)
                          T034 (US3 wire)
                                │
                                ▼
                       T035-T040 (polish, smoke, PR)
```

The three user stories are independent in their data layer (different tables) and can ship in priority order: US1 alone is a useful product, US2 adds, US3 finishes.

## Parallel execution examples

- **Foundational tests**: `T006 [P]` (storage init), `T007 [P]` (L2 client check), `T008 [P]` (sidebar check) — three disjoint files.
- **US1 tests**: `T009 [P]`, `T010 [P]`, `T011 [P]` — L2 pytest, L1 Vitest page test, L1 Vitest picker test. Different files, no shared state.
- **US1 components**: `T017 [P]` (logo-grid) + `T018 [P]` (saved-logo-picker) — separate component files.

## MVP scope

- Phase 1 + Phase 2 + US1 (T001 through T020) is the minimum useful release. Saves logos, surfaces them in Mode 2's wizard.
- US2 + US3 ship together with US1 in a single PR, since they share `brand_library.py` route module and `brand_store.py` store, but each can land separately if review prefers it.
