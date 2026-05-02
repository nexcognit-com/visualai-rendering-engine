---
description: "Task list for feature 009 — Static Brand Overlays on Rendered Videos"
---

# Tasks: Static Brand Overlays on Rendered Videos

**Input**: Design documents from `/specs/009-brand-overlays/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Smoke tests are MANDATORY for this feature per the constitution's §Development Workflow rule ("new mode code requires at least one smoke test exercising the rendering path with mocked Layer 2 inputs"). The contracts in `contracts/` define 16 acceptance tests (UE-1..UE-8 + C-1..C-8); these are scheduled as task items below.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. The four user stories from spec.md are:

- **US1** (P1): Logo overlay — user uploads a PNG, picks a corner, sees it in the final MP4
- **US2** (P2): Rectangle overlay — user picks corner + size + color + opacity, sees a static rectangle
- **US3** (P3): Multi-overlay stacking — multiple overlays in one render with deterministic z-order
- **US4** (P3): Brand Library forward-compat — schema accepts future Brand Library asset paths (schema-only test)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4)
- All file paths are absolute or relative to the project root `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: minimal preparation; this is a mid-project feature, not a fresh init.

- [ ] T001 Confirm `storage/uploads/` is gitignored (inspect `.gitignore`; if `storage/` itself isn't ignored, add `storage/uploads/` explicitly). Path: `.gitignore`.
- [ ] T002 [P] Create test helper `_make_stub_video(path: str, duration_s: float = 1.0)` and `_make_synthetic_logo(path: str, color: tuple[int, int, int] = (255, 248, 107))` in `test/services/test_helpers.py` so overlay smoke tests can produce ColorClip stubs and Pillow PNGs without committed fixtures (see [research.md R7](./research.md)).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared backend + client primitives every user story depends on. The compositor's logo+rectangle branches and the schema's both-kinds support are deliberately built up-front so each user story owns only its own wizard panel + tests.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Backend (Layer 3)

- [ ] T003 Add `Overlay` Pydantic v2 model (logo + rectangle discriminated union) AND extend `VideoParams` with `overlays: list[Overlay] = []` (max_length=5). Implement the `model_validator(mode="after")` per [data-model.md §Entity 1](./data-model.md). Path: `app/models/schema.py`.
- [ ] T004 [P] Create `OverlayError(code: str, **context)` exception class and `apply_overlays(input_mp4: str, overlays: list[Overlay], output_mp4: str | None = None) -> str` skeleton with empty-list fast path + position-math helper. Implement BOTH logo and rectangle branches per [contracts/compositor-contract.md](./contracts/compositor-contract.md). Path: `app/services/overlays.py`.
- [ ] T005 [P] Create `POST /api/v1/uploads/logo` endpoint per [contracts/upload-endpoint.md](./contracts/upload-endpoint.md) using FastAPI `UploadFile` + `File()`. Validate MIME (PNG/JPG/WebP), size (≤ 5 MB), Pillow open-as-image; save with UUID4 filename + MIME-derived extension; return `{path, size_bytes, mime_type}`. Path: `app/controllers/v1/uploads.py`.
- [ ] T006 Register the uploads router in the application root router. Path: `app/router.py` (add `root_api_router.include_router(uploads.router)` alongside the existing `video.router` and `llm.router` lines around line 16).
- [ ] T007 Wire the overlay step into the task pipeline: after `combine_videos()` produces the stitched MP4, if `params.overlays` is non-empty, call `apply_overlays(...)` and use its return path as the user-facing final. Path: `app/services/task.py`. **Note**: this is the second touch line on `task.py` (the first is the existing Step 1 `mode=` plumbing), continuing tracked debt #5 in `STEP1_DEBT.md`.

### Frontend (Layer 1)

- [ ] T008 [P] Create the TypeScript `Overlay` type matching [contracts/overlay-schema.md](./contracts/overlay-schema.md) — discriminated union by `kind` with logo and rectangle variants. Path: `visualai-frontend/src/lib/overlay.ts`.
- [ ] T009 [P] Create the frontend multipart proxy at `visualai-frontend/src/app/api/upload-logo/route.ts` that accepts `multipart/form-data` from the browser, re-multiparts to MPT's `/api/v1/uploads/logo`, and forwards the JSON response (or error). Path: `visualai-frontend/src/app/api/upload-logo/route.ts`.
- [ ] T010 Extend the existing `/api/generate` proxy to pass `overlays` (typed as `Overlay[]`) through the request body to MPT alongside the existing `video_subject`/`mode`/etc. fields. Path: `visualai-frontend/src/app/api/generate/route.ts`. (Depends on T008 for the type.)

**Checkpoint**: Foundation ready. The full backend pipeline accepts and processes overlays end-to-end; the frontend has the types and API plumbing. User story implementation can now begin in parallel.

---

## Phase 3: User Story 1 — Logo Overlay (Priority: P1) 🎯 MVP

**Goal**: A user uploads a logo PNG, picks a corner, submits the wizard, and sees the logo composited cleanly in every frame of the final MP4. Solves the user-visible "agent ignores my instructions" friction that motivated this spec.

**Independent Test**: Generate two Mode 2 videos for the same subject — one with no overlay, one with a logo overlay. The first MUST match today's pipeline output exactly (zero regression). The second MUST have the logo crisply composited in the picked corner of every frame.

### Tests for User Story 1 (mandatory smoke + contract tests)

- [ ] T011 [P] [US1] Smoke test C-1 (empty-list fast path): `apply_overlays(stub_video, [])` returns input path unchanged; assert no new file written; elapsed time < 10 ms. Path: `test/services/test_overlays.py`.
- [ ] T012 [P] [US1] Smoke test C-2 (single logo composite): build a 1 s ColorClip stub + a synthetic transparent PNG via Pillow; call `apply_overlays(...)` with a logo at `top-right`, `width_pct=0.15`; assert output exists and the top-right region's mean RGB shifted toward the logo color. Path: `test/services/test_overlays.py`.
- [ ] T013 [P] [US1] Smoke test C-5 (logo file missing): `apply_overlays(stub_video, [Overlay(kind="logo", source_path="/nope.png", ...)])` raises `OverlayError(code="logo_not_found")`. Path: `test/services/test_overlays.py`.
- [ ] T014 [P] [US1] Smoke test C-7 (corrupt PNG): write `not a real png` bytes to `tmp_path/broken.png`; assert `apply_overlays` raises `OverlayError(code="logo_unreadable")`. Path: `test/services/test_overlays.py`.
- [ ] T015 [P] [US1] Contract test UE-1 + UE-2 + UE-3 (valid uploads): POST a Pillow-generated PNG, JPG, and WebP each ≤ 5 MB to `/api/v1/uploads/logo`; assert HTTP 201, body has `path` matching `^storage/uploads/[0-9a-f-]{36}\.(png|jpg|webp)$`. Path: `test/controllers/test_uploads.py`.
- [ ] T016 [P] [US1] Contract test UE-4 + UE-5 + UE-6 (rejected uploads): a TIFF returns 400 `unsupported_format`; a 6 MB PNG returns 413 `file_too_large`; an empty file returns 400 `empty_upload`. Path: `test/controllers/test_uploads.py`.
- [ ] T017 [P] [US1] Contract test UE-7 (corrupt image): plain text bytes claiming `image/png` MIME returns 415 `invalid_image`. Path: `test/controllers/test_uploads.py`.
- [ ] T018 [P] [US1] Contract test UE-8 (filename safety): upload with filename `../../etc/passwd.png` returns 201, but the stored filename is a UUID4 (NOT path-traversal-preserved). Assert the response `path` field starts with `storage/uploads/` and ends with `.png`. Path: `test/controllers/test_uploads.py`.

### Implementation for User Story 1

- [ ] T019 [US1] Add the collapsed "Overlays" panel scaffolding to wizard Step 3, alongside the existing voice + music selectors: panel header + collapse/expand state + "Add overlay" button (initially "Add logo" only — rectangle ships in US2). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`.
- [ ] T020 [US1] Build the Logo overlay form: hidden `<input type="file" accept="image/png,image/jpeg,image/webp">` triggered by a styled button, corner picker (5 buttons for the position enum), opacity slider (10–100%), width slider (5–40% of video width). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T019.)
- [ ] T021 [US1] Wire the file input to the `/api/upload-logo` proxy: on file change, validate client-side (size ≤ 5 MB, MIME in allowed list), POST as `FormData`, store the returned `path` in wizard state as the `Overlay.source_path`. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T020.)
- [ ] T022 [US1] Surface upload errors inline near the file input (FR-010): show typed messages for `unsupported_format`, `file_too_large`, `invalid_image`, `storage_write_failed`; render does NOT start while errors are unresolved. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T021.)
- [ ] T023 [US1] Pass the in-state `overlays` array through the wizard's submit call to `/api/generate` (the proxy already accepts the field after T010). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T020.)
- [ ] T024 [US1] Run [quickstart.md Part 2](./quickstart.md) (manual end-to-end logo verification) and confirm SC-001 pass criteria: logo crisply composited in picked corner, transparency preserved, no regression in render time vs the no-overlay baseline. Path: manual verification, no file change.

**Checkpoint**: User Story 1 fully functional. Logo overlays work end-to-end through the wizard. MVP delivered.

---

## Phase 4: User Story 2 — Rectangle Overlay (Priority: P2)

**Goal**: A user picks a corner, a size preset, a color, and an opacity in the wizard, submits, and sees a static rectangle composited in every frame.

**Independent Test**: Generate a Mode 2 video with a single rectangle overlay (e.g., bottom-left, medium, brand-accent blue, 60% opacity). The final MP4 MUST show that rectangle in every frame at the specified position, color, and opacity. No interaction with US1's logo path needed.

### Tests for User Story 2

- [ ] T025 [P] [US2] Smoke test C-3 (single rectangle composite): build a 1 s ColorClip stub; call `apply_overlays(...)` with `Overlay(kind="rectangle", color="#FFFFFF", size_preset="medium", position="bottom-left", opacity=0.5)`; assert the bottom-left region's mean RGB shifted toward white. Path: `test/services/test_overlays.py`.

### Implementation for User Story 2

- [ ] T026 [US2] Extend the wizard's Overlays panel to include "Add rectangle" alongside "Add logo" — entries differ by `kind` field set on creation. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T019.)
- [ ] T027 [US2] Build the Rectangle overlay form: corner picker (same 5-button enum as logo), size preset radio (small/medium/large), color picker (hex input + a small preset palette including spec 001's `--color-accent` `#3B82F6` and `--color-bg-elevated` `#1E293B`), opacity slider (10–100%). Validate `^#[0-9A-Fa-f]{6}$` for hex input. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T026.)
- [ ] T028 [US2] Run [quickstart.md Part 3](./quickstart.md) (manual rectangle verification): rectangle visible in the picked corner, correct size preset, correct color + opacity. Path: manual verification.

**Checkpoint**: User Story 2 complete. User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 — Multi-Overlay Stacking (Priority: P3)

**Goal**: A user adds a logo AND a rectangle (or N overlays of any mix) to the same render and sees them composited in deterministic z-order (later in list = higher z-index).

**Independent Test**: Configure one logo + one rectangle in the same wizard submission. The rendered MP4 MUST contain BOTH overlays at their picked positions; the logo MUST appear on top of the rectangle (later in the list).

### Tests for User Story 3

- [ ] T029 [P] [US3] Smoke test C-4 (stacked overlays z-order): build a 1 s stub; call `apply_overlays(...)` with `[Overlay(kind="rectangle", ...), Overlay(kind="logo", ...)]` at the SAME corner; assert the logo's color dominates the overlap region (proves logo is on top because it's later in the list). Path: `test/services/test_overlays.py`.

### Implementation for User Story 3

- [ ] T030 [US3] Allow multiple overlays in the wizard: "Add overlay" button creates additional entries; each entry has a remove (×) button; enforce client-side max of 5 entries per FR-010. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T020 + T026.)
- [ ] T031 [US3] Run [quickstart.md Part 4](./quickstart.md) (manual multi-overlay z-order verification): logo composited on top of rectangle when both pinned to the same corner. Path: manual verification.

**Checkpoint**: User Story 3 complete. All three primary stories work independently.

---

## Phase 6: User Story 4 — Brand Library Forward-Compat (Priority: P3, schema-only)

**Goal**: The v1 `Overlay.source_path` field accepts future Brand Library asset paths (`brand-library/<tenant_id>/<asset>.png`) without schema change, satisfying SC-006 and FR-012.

**Independent Test**: A synthetic `Overlay` payload with `source_path: "brand-library/tenant_abc/logo_v2.png"` validates against the v1 Pydantic model with no errors.

### Tests for User Story 4

- [ ] T032 [P] [US4] Schema test SC-006: instantiate `Overlay(kind="logo", position="bottom-right", source_path="brand-library/tenant_abc/logo_v2.png", width_pct=0.15, opacity=1.0)`; assert it validates cleanly. Path: `test/models/test_schema_overlay.py`.

**Checkpoint**: Forward-compat hook locked in; future Brand Library work won't require a schema migration.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: tasks that span multiple stories or finalize the feature for merge.

- [ ] T033 [P] Smoke test C-6 (base video missing): `apply_overlays("/nope.mp4", [Overlay(...)])` raises `OverlayError(code="base_video_missing")`. Path: `test/services/test_overlays.py`.
- [ ] T034 [P] Smoke test C-8 (output collision): pre-create the default output path on disk; call `apply_overlays` with overlays present; assert it raises `OverlayError(code="output_collision")`. Path: `test/services/test_overlays.py`.
- [ ] T035 [P] Surface "this render had overlays" indicator on the My Assets card when `task.overlays` was non-empty (FR-011). Pull the `overlays` array from the existing `script.json` artifact in `app/api/history/route.ts` and render a small badge in the My Assets grid. Path: `visualai-frontend/src/app/api/history/route.ts` and `visualai-frontend/src/app/assets/page.tsx`.
- [ ] T036 Update `STEP1_DEBT.md` row #5 with a note that this feature added a second `task.py` touch line; both lines repay together at Step 3 when the mode registry lands. Path: `STEP1_DEBT.md`.
- [ ] T037 [P] Run [quickstart.md Parts 1, 5a, 5b, 5c, 6, 7](./quickstart.md): verify SC-002 zero-regression, all error-surfacing paths, full pytest run, and SC-006 forward-compat. Path: manual verification.
- [ ] T038 Constitution compliance check: `git diff --stat origin/main..HEAD` must show ZERO changes to `app/services/video.py` (Principle II rebase-clean rule). If any line of `video.py` changed, abort the merge. Path: manual verification.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. **BLOCKS all user stories.**
- **User Stories (Phase 3+)**: All depend on Foundational completion.
  - US1 (P1) is the MVP — ship and validate independently.
  - US2 (P2) and US3 (P3) build on the same wizard panel but exercise different overlay kinds.
  - US4 (P3) is a single schema test, runnable any time after T003.
- **Polish (Phase 7)**: Depends on all desired user stories being complete.

### Within Each User Story

- Tests MUST exist and FAIL before implementation (constitution: smoke tests required for new render-pipeline code).
- Backend foundational work (Phase 2) precedes any wizard UI changes.
- Wizard panel scaffolding (T019) precedes overlay-form work (T020, T026).
- Quickstart-validation tasks (T024, T028, T031) close out each story after implementation.

### File Conflicts to Note

- `app/models/schema.py` — touched once (T003). Sequential with anything else editing schema.py.
- `app/services/overlays.py` — touched once (T004). All test cases (T011..T014, T025, T029, T033, T034) read it but don't modify.
- `app/services/task.py` — touched once (T007). Sequential.
- `app/router.py` — touched once (T006). Sequential.
- `visualai-frontend/src/app/modes/short-video/page.tsx` — touched by T019, T020, T021, T022, T023, T026, T027, T030. **All sequential** (same file). No `[P]` allowed on these.
- `visualai-frontend/src/app/api/generate/route.ts` — touched once (T010).
- `visualai-frontend/src/app/api/history/route.ts` — touched once (T035).
- `visualai-frontend/src/app/assets/page.tsx` — touched once (T035).
- `test/services/test_overlays.py` — multiple test cases, can be developed in parallel as separate test functions (T011, T012, T013, T014, T025, T029, T033, T034 all `[P]` because pytest collects functions independently within the same file).
- `test/controllers/test_uploads.py` — multiple test cases (T015, T016, T017, T018) `[P]`.
- `test/models/test_schema_overlay.py` — single task (T032).

### Parallel Opportunities

- **Phase 1**: T002 alone is parallelizable; T001 is trivial and sequential.
- **Phase 2 backend**: T004, T005 can run in parallel (different files); T003, T006, T007 sequential due to file dependencies.
- **Phase 2 frontend**: T008, T009 can run in parallel (different files); T010 depends on T008.
- **Phase 3 tests**: T011..T018 all `[P]` — different test functions, different files; pytest allows parallel collection.
- **Phase 3 implementation**: T019..T023 sequential (same wizard file); T024 manual.
- **Phase 4–6 tests**: each `[P]`.
- **Phase 7**: T033, T034, T035, T037 `[P]`; T036, T038 sequential.

---

## Parallel Example: User Story 1 Tests

```bash
# All US1 backend tests can be developed in parallel (different test functions):
Task: "Smoke test C-1 (empty-list fast path) in test/services/test_overlays.py"
Task: "Smoke test C-2 (single logo composite) in test/services/test_overlays.py"
Task: "Smoke test C-5 (logo file missing) in test/services/test_overlays.py"
Task: "Smoke test C-7 (corrupt PNG) in test/services/test_overlays.py"

# All US1 upload contract tests can run in parallel:
Task: "Contract test UE-1/UE-2/UE-3 (valid uploads) in test/controllers/test_uploads.py"
Task: "Contract test UE-4/UE-5/UE-6 (rejected uploads) in test/controllers/test_uploads.py"
Task: "Contract test UE-7 (corrupt image) in test/controllers/test_uploads.py"
Task: "Contract test UE-8 (filename safety) in test/controllers/test_uploads.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002).
2. Complete Phase 2: Foundational (T003..T010). **CRITICAL — blocks all stories.**
3. Complete Phase 3: User Story 1 (T011..T024).
4. **STOP and VALIDATE**: run [quickstart.md Part 2](./quickstart.md). Confirm SC-001 pass criteria.
5. Demo / merge as PR if ready.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready (~1 hour).
2. Add User Story 1 → Ship (MVP); ~1.5 hours of UI + ~30 min of tests.
3. Add User Story 2 → Ship; ~30 min (most of the UI is reused from US1).
4. Add User Story 3 → Ship; ~20 min.
5. Add User Story 4 schema test → Ship; ~5 min (one test).
6. Polish → ~1 hour total.

**Total estimated time**: 4–5 hours single-developer, single-session. Substantially shorter than the original "build a CV-pipeline" framing this feature replaced.

### Constitution Compliance Reminders

- **Do not edit `app/services/video.py`** (Principle II — keep upstream MoviePy assembly code rebase-clean). T038 verifies.
- The PR description for this feature MUST reference Mode 2 (Short Marketing Video) and cite Master Spec §3 (Five Agent Modes) per the constitution's §Development Workflow rule for fork-surface PRs.
- The smoke tests at `test/services/test_overlays.py` are a hard requirement — the PR MUST NOT merge without them passing locally (and the constitution requires `pytest test/` pass before opening a PR).

---

## Notes

- `[P]` tasks = different files, no dependencies — can run in parallel.
- `[Story]` label maps task to specific user story for traceability and independent delivery.
- Each user story is independently completable and testable; halting after US1 ships a real MVP.
- The 16 contract acceptance tests (UE-1..UE-8 + C-1..C-8) are scheduled across Phase 3 (US1 owns 12 of them — logo + upload tests), Phase 4 (US2 owns 1 — rectangle test), Phase 5 (US3 owns 1 — stacking test), and Phase 7 (the remaining 2 — base-missing + output-collision are not story-specific).
- Commit after each task or logical group. The full feature is one PR per the SpecKit governance pattern; intra-feature commits are encouraged for review-ability.
