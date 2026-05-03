# Tasks: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Branch**: `015-modes-1-5-registry` | **Date**: 2026-05-03
**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)
**Tests**: Spec calls for tests on every layer (registry, material rewrite, Layer 2 routes, Layer 2.5 router, frontend helpers). Tests are INCLUDED.

**Repo legend**: `L3` = this repo (MoneyPrinterTurbo, Layer 3); `L2` = `../visualai-orchestration/` (Layer 2); `L1` = `../visualai-frontend/` (Layer 1).

PR slicing per [research.md §PR slicing recommendation](research.md):
- **PR-A** (lands first): Phases 1, 2, 3, 5 (Mode 5 + registry + material rewrite + constitution amendment)
- **PR-B** (rebases on PR-A): Phases 4, 6 (Mode 1 + Layer 2.5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo-level scaffolding that every story depends on.

- [ ] T001 [P] [L3] Create empty `app/services/modes/` directory with `__init__.py` placeholder (returns `KeyError` for everything for now) so imports don't break before T013 lands. Path: `app/services/modes/__init__.py`
- [ ] T002 [P] [L3] Add `app/services/modes/_interface.py` with the `Mode` Protocol per [contracts/modes-registry-interface.md §1](contracts/modes-registry-interface.md). Path: `app/services/modes/_interface.py`
- [ ] T003 [P] [L2] Create empty `app/router/` package directory with `__init__.py` (re-export stub for `generate_studio_photos`). Path: `../visualai-orchestration/app/router/__init__.py`
- [ ] T004 [P] [L2] Create `app/router/exceptions.py` with `ProviderTimeout`, `ProviderError`, `ProviderInvalidResponse` exception classes per [contracts/layer25-image-router.md §4](contracts/layer25-image-router.md). Path: `../visualai-orchestration/app/router/exceptions.py`
- [ ] T005 [P] [L2] Add `LAYER2_SIGNING_KEY`, `LAYER25_IMAGE_PROVIDER`, `LAYER25_NANOBANANA_API_KEY`, `LAYER25_NANOBANANA_TIMEOUT_S` to `.env.example` with placeholder values. Path: `../visualai-orchestration/.env.example`
- [ ] T006 [P] [L2] Add same vars to `app/config.py` `Settings` class with appropriate types + defaults per [contracts/layer2-product-shoots-api.md §8](contracts/layer2-product-shoots-api.md). Path: `../visualai-orchestration/app/config.py`
- [ ] T007 [P] [L1] Add `LAYER2_DEMO_BEARER_TOKEN` (existing) + `NEXT_PUBLIC_DASHBOARD_MODES` to `.env.local.example`. Path: `../visualai-frontend/.env.local.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-cutting infra that every user story depends on. **NO user-story work until this phase is checkpointed.**

- [ ] T008 [L3] Widen `VideoParams.mode` literal from `["short", "faceless"]` to `["short", "faceless", "product_shoot"]` with default `"short"` (preserves backwards compat) in `app/models/schema.py`. Path: `app/models/schema.py`
- [ ] T009 [L3] Add controller-level guard in `app/controllers/v1/videos.py`: reject `params.mode == "product_shoot"` with `HTTPException(422, {"error_code": "unsupported_mode_for_render"})` BEFORE `task_manager.add_task` is called. Path: `app/controllers/v1/videos.py`
- [ ] T010 [P] [L2] Implement `app/auth/pre_signer.py`: `sign_url(tenant_id, filename, ttl_seconds=900) -> str` and `verify_url(url) -> tuple[str, str]` (returns tenant_id + filename or raises) per [data-model.md E5](data-model.md). Path: `../visualai-orchestration/app/auth/pre_signer.py`
- [ ] T011 [P] [L2] Implement `app/routes/pre_signed.py` exposing `GET /_signed/{sig}/{tenant_id}/{filename}` with HMAC + expiry + path-traversal validation per [research.md R4](research.md). Path: `../visualai-orchestration/app/routes/pre_signed.py`
- [ ] T012 [L2] Register the `pre_signed` router in `main.py` BEFORE the JWT middleware (signed URLs use HMAC, not JWT, so they must bypass JWT enforcement). Path: `../visualai-orchestration/main.py`
- [ ] T013 [P] [L2] Add production-safety check at startup: refuse to start when `LAYER2_SIGNING_KEY` is missing, empty, or `"changeme"` (parallel to existing JWT signing-key check). Path: `../visualai-orchestration/app/auth/jwt_auth.py` (extend `verify_production_safety`)
- [ ] T014 [P] [L2] Tests: `tests/auth/test_pre_signer.py` covering sign+verify roundtrip, tampered sig, expired URL, cross-tenant pattern, path-traversal attempts. Path: `../visualai-orchestration/tests/auth/test_pre_signer.py`
- [ ] T015 [P] [L2] Tests: `tests/routes/test_pre_signed.py` covering 200/403/410/404 paths per [contracts/layer2-product-shoots-api.md §3.2](contracts/layer2-product-shoots-api.md). Path: `../visualai-orchestration/tests/routes/test_pre_signed.py`

**Checkpoint**: Pre-signed URL handshake works end-to-end (mint via `sign_url`, fetch via `/_signed/...`). All Phase-2 tests green. User stories can now proceed.

---

## Phase 3: User Story 1 — Mode 5 Faceless Channel (Priority: P1) — PR-A

**Goal**: Activate Faceless Channel card; Mode 5 dispatches via `app/services/modes/faceless.py`; `material.py` accepts pre-signed URLs OR falls back to direct Pexels for Mode 5 only.

**Independent Test**: User clicks Faceless Channel card → enters topic → gets 9:16 MP4 within 90s. `script.json#params.mode == "faceless"`. Layer 3 logs show `material.download_videos source=pexels_direct`.

### Tests for User Story 1 (write FIRST, ensure they FAIL before implementation)

- [ ] T016 [P] [US1] [L3] `test/services/modes/__init__.py` (empty file to make it a package). Path: `test/services/modes/__init__.py`
- [ ] T017 [P] [US1] [L3] `test/services/modes/test_registry.py` — REG-1..REG-7 cases per [contracts/modes-registry-interface.md §5.1](contracts/modes-registry-interface.md). Path: `test/services/modes/test_registry.py`
- [ ] T018 [P] [US1] [L3] `test/services/modes/test_faceless.py` — FACE-1..FACE-4 cases per [contracts/modes-registry-interface.md §5.3](contracts/modes-registry-interface.md). Path: `test/services/modes/test_faceless.py`
- [ ] T019 [P] [US1] [L3] `test/services/modes/test_short.py` — SHORT-1..SHORT-5 cases per [contracts/modes-registry-interface.md §5.2](contracts/modes-registry-interface.md). Path: `test/services/modes/test_short.py`
- [ ] T020 [P] [US1] [L3] `test/services/test_material_pre_signed_urls.py` — MAT-1..MAT-10 cases per [contracts/material-pre-signed-urls.md §7.1](contracts/material-pre-signed-urls.md). Path: `test/services/test_material_pre_signed_urls.py`

### Implementation for User Story 1 — Layer 3 mode registry + material rewrite

- [ ] T021 [US1] [L3] Implement `app/services/modes/short.py` — Mode 2 module exporting `name`, `default_aspect_ratio`, `generate_script`, `generate_terms`, `select_visuals_strategy`. Move marketing-script + setting-tag helpers from `llm.py` per [contracts/modes-registry-interface.md §3.1](contracts/modes-registry-interface.md). Path: `app/services/modes/short.py`
- [ ] T022 [US1] [L3] Implement `app/services/modes/faceless.py` — Mode 5 module exporting the same Protocol. Topic-driven script + generic Pexels-friendly terms per [contracts/modes-registry-interface.md §3.2](contracts/modes-registry-interface.md). Path: `app/services/modes/faceless.py`
- [ ] T023 [US1] [L3] Implement registry dispatcher in `app/services/modes/__init__.py`: `_REGISTRY` dict, `pick(name)`, `supported()`. Replace placeholder from T001. Path: `app/services/modes/__init__.py`
- [ ] T024 [US1] [L3] Shrink `app/services/llm.py`: remove `generate_marketing_script`, mode=="short" branches in `generate_script` / `generate_terms`. Keep generic LLM helpers + `polish_script` (spec 013). Path: `app/services/llm.py`
- [ ] T025 [US1] [L3] Refactor `app/services/task.py`: replace inline mode dispatch with `modes.pick(params.mode).generate_script(...)` and `.generate_terms(...)`. Preserve script_mode auto/verbatim/polish branching from spec 013 OUTSIDE the registry call per [contracts/modes-registry-interface.md §4](contracts/modes-registry-interface.md). Path: `app/services/task.py`
- [ ] T026 [US1] [L3] Rewrite `app/services/material.py`: read `pre_signed_clip_urls` from `visuals.json` sidecar, branch dispatch tree per [contracts/material-pre-signed-urls.md §2-§3](contracts/material-pre-signed-urls.md). Mode 5 path keeps existing `_search_stock_dual_source` byte-for-byte. Path: `app/services/material.py`
- [ ] T027 [US1] [L3] Add structured Loguru logging in `material.py` per [contracts/material-pre-signed-urls.md §8](contracts/material-pre-signed-urls.md): `tenant_id`, `user_id`, `mode`, `source` (`pre_signed` | `pexels_direct` | `user_uploaded`), `url_count`. Path: `app/services/material.py`

### Implementation for User Story 1 — Layer 2 sidecar writer for Mode 5

- [ ] T028 [US1] [L2] Extend `app/routes/videos.py`: when `mode == "faceless"`, write `visuals.json` sidecar with `pre_signed_clip_urls: null` (signals Layer 3 to use Pexels direct). Path: `../visualai-orchestration/app/routes/videos.py`
- [ ] T029 [P] [US1] [L2] Tests: `tests/routes/test_videos_faceless.py` — POST with mode=faceless writes sidecar with `pre_signed_clip_urls: null`. Path: `../visualai-orchestration/tests/routes/test_videos_faceless.py`

### Implementation for User Story 1 — Layer 1 Mode 5 wizard

- [ ] T030 [P] [US1] [L1] Activate Mode 5 dashboard card: in `src/app/page.tsx`, change `faceless-channel` card config to `href: "/modes/faceless-channel"`, remove "Coming in Step 3" badge per [contracts/frontend-mode-1-5-wizards.md §1](contracts/frontend-mode-1-5-wizards.md). Path: `../visualai-frontend/src/app/page.tsx`
- [ ] T031 [P] [US1] [L1] Create `src/app/modes/faceless-channel/page.tsx` — 3-step wizard (topic + voice/music + progress) per [contracts/frontend-mode-1-5-wizards.md §2](contracts/frontend-mode-1-5-wizards.md). Path: `../visualai-frontend/src/app/modes/faceless-channel/page.tsx`
- [ ] T032 [US1] [L1] Extend `src/app/api/generate/route.ts` to forward `mode` field if present (already does — verify). Path: `../visualai-frontend/src/app/api/generate/route.ts`

**Checkpoint**: Mode 5 end-to-end works. Quickstart Step C passes. All Phase-3 tests green. PR-A is now complete EXCEPT for STEP1_DEBT.md updates (T056) and constitution amendment (T055), which land in Phase 5.

---

## Phase 4: User Story 2 — Mode 1 Product Shoot Generator (Priority: P1) — PR-B

**Goal**: Activate Product Shoot card; user uploads one image → 6 studio photos via NanoBanana Pro → Layer 2 + Layer 2.5 only; Layer 3 untouched.

**Independent Test**: User clicks Product Shoot card → uploads photo → gets 6 studio photos in grid within 60s. Layer 3 logs show ZERO activity. Layer 2 logs show NanoBanana call + cost log.

### Tests for User Story 2 (write FIRST)

- [ ] T033 [P] [US2] [L2] `tests/router/test_image.py` — IR-1..IR-11 cases per [contracts/layer25-image-router.md §6.1](contracts/layer25-image-router.md). Use `respx` to mock NanoBanana. Path: `../visualai-orchestration/tests/router/test_image.py`
- [ ] T034 [P] [US2] [L2] `tests/router/test_slicing.py` — SL-1..SL-5 cases per [contracts/layer25-image-router.md §6.2](contracts/layer25-image-router.md). Path: `../visualai-orchestration/tests/router/test_slicing.py`
- [ ] T035 [P] [US2] [L2] `tests/routes/test_product_shoots.py` — PS-1..PS-15 cases per [contracts/layer2-product-shoots-api.md §6.1](contracts/layer2-product-shoots-api.md). Path: `../visualai-orchestration/tests/routes/test_product_shoots.py`
- [ ] T036 [P] [US2] [L1] `tests/product-shoot.test.ts` (Vitest) — FE-PS-T1..FE-PS-T5 cases per [contracts/frontend-mode-1-5-wizards.md §6.1](contracts/frontend-mode-1-5-wizards.md). Path: `../visualai-frontend/tests/product-shoot.test.ts`

### Implementation for User Story 2 — Layer 2.5 image router

- [ ] T037 [P] [US2] [L2] Implement `app/router/_slicing.py`: `slice_3x2_contact_sheet(bytes) -> list[bytes]` and `looks_like_contact_sheet(bytes) -> bool` per [contracts/layer25-image-router.md §5](contracts/layer25-image-router.md). Path: `../visualai-orchestration/app/router/_slicing.py`
- [ ] T038 [P] [US2] [L2] Implement `app/router/_provider_nanobanana.py`: `name`, `async generate(...)` calling FAL.ai's `fal.run/fal-ai/nano-banana-pro/edit/multi` per [contracts/layer25-image-router.md §3.1](contracts/layer25-image-router.md). Path: `../visualai-orchestration/app/router/_provider_nanobanana.py`
- [ ] T039 [US2] [L2] Implement `app/router/image.py`: `async generate_studio_photos(...)` provider lookup + contact-sheet detection + slicing dispatch + writes 6 jpgs to `output_dir` per [contracts/layer25-image-router.md §1-§2](contracts/layer25-image-router.md). Path: `../visualai-orchestration/app/router/image.py`
- [ ] T040 [US2] [L2] Wire `app/router/__init__.py` to export `generate_studio_photos`. Path: `../visualai-orchestration/app/router/__init__.py`

### Implementation for User Story 2 — Layer 2 product-shoots route

- [ ] T041 [P] [US2] [L2] Create Pydantic models in `app/models/product_shoot.py`: `ProductShootRequest`, `ProductShootGeneration` per [data-model.md E4](data-model.md). Path: `../visualai-orchestration/app/models/product_shoot.py`
- [ ] T042 [US2] [L2] In-memory store helper `app/services/product_shoot_store.py`: dict-keyed registry for `ProductShootGeneration` records (Step-3 stand-in for the Step-4 Neon table). Path: `../visualai-orchestration/app/services/product_shoot_store.py`
- [ ] T043 [US2] [L2] Implement `app/routes/product_shoots.py` with `POST /api/v1/product-shoots` per [contracts/layer2-product-shoots-api.md §1-§4](contracts/layer2-product-shoots-api.md). JWT-protected via existing middleware. Path: `../visualai-orchestration/app/routes/product_shoots.py`
- [ ] T044 [US2] [L2] Register `product_shoots` router in `main.py` (downstream of JWT middleware). Path: `../visualai-orchestration/main.py`
- [ ] T045 [US2] [L2] Add structured Loguru logging in `product_shoots.py` per [contracts/layer2-product-shoots-api.md §7](contracts/layer2-product-shoots-api.md): `generation_id`, `tenant_id`, `user_id`, `mode="product_shoot"`, `provider`, `latency_ms`, `cost_estimate_usd`. Path: `../visualai-orchestration/app/routes/product_shoots.py`

### Implementation for User Story 2 — Layer 1 Product Shoot wizard

- [ ] T046 [P] [US2] [L1] Activate Mode 1 dashboard card in `src/app/page.tsx`: `product-shoot` card → `href: "/modes/product-shoot"`, remove "Coming in Step 3" badge. Path: `../visualai-frontend/src/app/page.tsx`
- [ ] T047 [P] [US2] [L1] Create `src/lib/product-shoot.ts` with types + `validateProductShootForm()` per [contracts/frontend-mode-1-5-wizards.md §5](contracts/frontend-mode-1-5-wizards.md). Path: `../visualai-frontend/src/lib/product-shoot.ts`
- [ ] T048 [P] [US2] [L1] Create `src/app/modes/product-shoot/page.tsx` — 2-step wizard (upload + result grid) per [contracts/frontend-mode-1-5-wizards.md §3](contracts/frontend-mode-1-5-wizards.md). Path: `../visualai-frontend/src/app/modes/product-shoot/page.tsx`
- [ ] T049 [US2] [L1] Create `src/app/api/product-shoot/route.ts` — proxy that uploads source image to Layer 2 then triggers Mode 1 generation per [contracts/frontend-mode-1-5-wizards.md §4](contracts/frontend-mode-1-5-wizards.md). Set `export const maxDuration = 120;`. Path: `../visualai-frontend/src/app/api/product-shoot/route.ts`

**Checkpoint**: Mode 1 end-to-end works. Quickstart Step D passes. All Phase-4 tests green. PR-B is now feature-complete EXCEPT for My Assets extension (T053) which lands in Phase 6.

---

## Phase 5: User Story 3 — Mode 2 zero-regression check (Priority: P1) — PR-A

**Goal**: Mode 2 keeps producing identical output after registry refactor + material.py rewrite. The user-story 1 implementation already does this work; this phase adds the verification gates.

**Independent Test**: Run identical Mode 2 inputs before/after Step 3 and compare. `script.json` byte-equal modulo timestamps. Render time within ±5%.

### Tests for User Story 3

- [ ] T050 [P] [US3] [L3] `test/services/test_mode_2_regression.py` — submit Mode 2 fixture inputs (visuals_mode=auto, user_uploaded, hybrid), assert produced `script.json` shape matches pinned snapshot. Path: `test/services/test_mode_2_regression.py`
- [ ] T051 [P] [US3] [L3] Manual regression checklist in `test/services/MODE_2_REGRESSION.md` — 3 fixed inputs to compare A/B before & after merge per [quickstart.md Step E](quickstart.md). Path: `test/services/MODE_2_REGRESSION.md`

**Checkpoint**: Quickstart Step E passes. T050 green.

---

## Phase 6: User Story 4 — Add a fourth mode without touching pipeline (Priority: P2) — PR-B

**Goal**: Demonstrate the registry's extensibility. A simulated "add Mode 6" exercise is the test.

**Independent Test**: Drop a stub mode module + register it + widen the literal. Submit a render with that mode. Verify dispatch reaches the stub without any `task.py` / `material.py` edits.

### Tests for User Story 4

- [ ] T052 [P] [US4] [L3] `test/services/modes/test_extensibility.py` — drops a temporary `_test_mode_six.py` module under `app/services/modes/` (cleanup in tearDown), registers it via monkeypatch on `_REGISTRY`, asserts `pick("test_mode_six")` returns it AND `task.generate_script` routes there without source edits. Path: `test/services/modes/test_extensibility.py`

### My Assets extension (Layer 1)

- [ ] T053 [US4] [L1] Extend My Assets page (`src/app/my-assets/page.tsx` or equivalent) to enumerate Mode 1 product-shoot generations alongside videos per FR-014. Use `GET /api/v1/my-assets` Layer 2 endpoint (extend if not present). Path: `../visualai-frontend/src/app/my-assets/page.tsx`

**Checkpoint**: T052 green. T053 surfaces Mode 1 outputs in My Assets.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Constitution amendment, debt-tracker updates, final smoke. Spans both PR-A (T054, T055, T056) and PR-B (T057, T058, T059).

### Constitution + debt tracker (PR-A)

- [ ] T054 [L3] Amend `.specify/memory/constitution.md` to v1.1.0 per [research.md R1](research.md): widen Principle II fork-surface enumeration to include `app/services/modes/`; bump version line; add Sync Impact Report entry. Path: `.specify/memory/constitution.md`
- [ ] T055 [L3] Update `.specify/memory/constitution.md` Mode set: mark Mode 1 + Mode 5 as "actively implemented" (was "reserved"). Path: `.specify/memory/constitution.md`
- [ ] T056 [L3] Update `STEP1_DEBT.md`: strike row #4 (Mode-Aware Rendering Contract) with `repaid in <commit-sha>`; strike row #5 (task.py outside fork-surface) with `repaid in <commit-sha>`; partially strike row #3 (External Asset Acceptance) — note "Mode 2 Auto path repaid; Mode 5 is permitted exception; Mode 2 hybrid path remaining as residual debt awaiting Step 3.5". Path: `STEP1_DEBT.md`

### Layer 2 storage + smoke (PR-B)

- [ ] T057 [L2] Verify `storage/uploads/<tenant_id>/` and `storage/tasks/<task_id>/` directories are created at startup if missing (FastAPI startup event). Path: `../visualai-orchestration/main.py`
- [ ] T058 [L2] Update README at `../visualai-orchestration/README.md` with Layer 2.5 router section: provider env vars, NanoBanana adapter, contact-sheet handling. Path: `../visualai-orchestration/README.md`

### Final smoke

- [ ] T059 [L3+L2+L1] Manual smoke test: walk through every step (A–I) in [quickstart.md](quickstart.md). Confirm all 9 pass criteria are checked. Document the run with timestamps + screenshots in `STEP3_SMOKE_NOTES.md` (transient, gitignored). Path: `STEP3_SMOKE_NOTES.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: independent — can start immediately, T001-T007 all parallel
- **Phase 2 (Foundational)**: T008 + T009 depend on T001-T002. T010-T015 (pre-signed URL infra) depend on T003-T006. **BLOCKS all user-story phases.**
- **Phase 3 (US1 Mode 5)**: depends on Phase 2 complete. Within US1: tests (T016-T020) before implementation (T021-T032).
- **Phase 4 (US2 Mode 1)**: depends on Phase 2 complete. Independent of Phase 3 — Mode 1 doesn't touch Layer 3, so it could land before Mode 5 in principle. Per PR slicing recommendation, Phase 3 lands as PR-A first; Phase 4 ships as PR-B rebased on PR-A.
- **Phase 5 (US3 Mode 2 regression)**: depends on Phase 3 complete (Mode 2 regression tests verify the registry refactor didn't break anything).
- **Phase 6 (US4 extensibility)**: depends on Phase 3 + Phase 4 complete.
- **Phase 7 (Polish)**: depends on all preceding phases. T054-T056 land with PR-A; T057-T059 land with PR-B.

### Within Each Phase

- Tests written and FAILING before implementation tasks start (red-green-refactor)
- Within tests, all `[P]` tests parallelize (different files)
- Within implementation, modify-same-file tasks must be sequential (e.g., T044 follows T043 because both edit `main.py`)

### Parallel opportunities

- Phase 1: ALL 7 tasks parallel (T001-T007).
- Phase 2: T008 → T009 sequential (T009 imports schema). T010-T015 mostly parallel.
- Phase 3: T016-T020 parallel (test files). T021-T024 sequential within `app/services/` because they cascade. T030-T032 parallel (frontend files).
- Phase 4: T033-T036 parallel (test files). T037-T040 sequential within `app/router/`. T041-T045 mostly sequential. T046-T049 parallel (frontend files).

---

## Implementation Strategy

### MVP First (User Story 1 — Mode 5 only)

Smallest demoable increment:

1. Phase 1 setup
2. Phase 2 foundational (pre-signed URLs work)
3. Phase 3 US1 (Mode 5 dispatches; registry exists; material.py rewritten)
4. Phase 5 US3 verification (Mode 2 didn't regress)
5. Phase 7 partial: T054-T056 (constitution + debt tracker)
6. Ship as **PR-A**. Demoable: Faceless Channel mode works; Mode 2 still works.

### Incremental Delivery

After PR-A merges:

1. Phase 4 US2 (Mode 1 — separate flow, Layer 2 + 2.5 only)
2. Phase 6 US4 verification (extensibility self-test)
3. Phase 7 remainder: T057-T059
4. Ship as **PR-B**. Demoable: Product Shoot mode works.

### Sequential single-developer flow (recommended for solo founder)

Today's expected order:

1. Phase 1 — 30 min
2. Phase 2 — 1.5h (pre-signed URL plumbing is the bulk)
3. Phase 3 — 3h (registry refactor + material.py rewrite + tests + Mode 5 wizard)
4. Phase 5 — 30 min (regression test pass)
5. Phase 7 PR-A subset — 30 min (constitution + debt tracker + commit + push)
6. **PR-A submitted. Stop, smoke, merge.**
7. Phase 4 — 2.5h (Layer 2.5 + Mode 1 wizard)
8. Phase 6 — 30 min (extensibility test + My Assets extension)
9. Phase 7 remainder — 30 min (storage + README + smoke)
10. **PR-B submitted.**

Total realistic estimate: ~10-12 hours including manual smoke + PR review.

---

## Notes

- `[P]` = parallelizable (different files, no shared state)
- `[L3] / [L2] / [L1]` = which repo the file lives in
- `[Story]` = traceable back to a user story in spec.md
- All tests written and FAILING before their corresponding implementation tasks
- Commit after each completed task or logical group
- After Phase 3 + Phase 5 + relevant Phase 7 tasks, **stop and smoke PR-A** before starting Phase 4
- `STEP1_DEBT.md` row #6 (Layer-3 upload carve-out) and row #7 (moderation) are intentionally NOT touched in Step 3 — they retire in Step 4 + Step 5 respectively
