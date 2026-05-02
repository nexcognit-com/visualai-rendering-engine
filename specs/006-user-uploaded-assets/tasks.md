# Tasks: User-Uploaded Model & Product Assets

**Feature**: 006-user-uploaded-assets
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)
**Date**: 2026-05-02

## Overview

Three user stories, prioritized:
- **US1 (P1)**: Generate Mode 2 video using ≥1 product photo (no model). MVP target.
- **US2 (P1)**: Add a model image that bookends opening + closing.
- **US3 (P2)**: Switch between Auto and My-assets mid-session, preserving uploaded asset state.

Tests are required (mirroring specs 010 + 013 precedent — backend pytest + frontend Vitest).

---

## Phase 1: Setup

- [~] T001 **DEFERRED** — STEP1_DEBT.md does not exist on the 006 branch's lineage (branched before debt tracker was introduced). Will be applied post-rebase onto main after PR #9 (spec 013) lands. Add two STEP1_DEBT.md cross-reference rows for spec 006: (a) Layer-3 upload carve-out continuing debts #1+#2, (b) `MODERATION_REQUIRED=False` Step-1 default carving out SC-006. Place in the existing cross-references table at the bottom of [STEP1_DEBT.md](../../STEP1_DEBT.md).

- [X] T002 [P] Add `image/jpeg`, `image/png`, `image/webp` validation constants and a 10 MB byte ceiling for spec 006 to the existing `_IMAGE_MIMES` and `_MAX_IMAGE_BYTES` constants in [app/controllers/v1/uploads.py](../../app/controllers/v1/uploads.py). Update the comment on `_IMAGE_MIMES` from "reserved for spec 009" to "used by spec 006 image upload + reserved for spec 009 logo uploads".

---

## Phase 2: Foundational

These tasks unblock both US1 and US2 (US3 depends on US1's frontend wiring landing).

- [X] T003 Extend `VideoParams` in [app/models/schema.py](../../app/models/schema.py) with `visuals_mode: Optional[Literal["auto", "user_uploaded"]] = None`, `uploaded_model_path: Optional[str] = None`, and `uploaded_product_paths: List[str] = Field(default_factory=list)`. Add a `@model_validator(mode="after")` named `_validate_visuals` that enforces: `visuals_mode == "user_uploaded"` → `uploaded_product_paths` length 1–3; all paths must resolve under `storage/uploads/` via `os.path.realpath().startswith()`. Raise `ValueError("no_product_assets" / "too_many_product_assets" / "path_outside_uploads")` on failure. Reference: [contracts/visuals-mode-wire-shape.md](contracts/visuals-mode-wire-shape.md).

- [X] T004 Write VW-1..VW-10 schema validation tests in `test/services/test_visuals_wire_shape.py` (new file). Cover legacy default, explicit `"auto"`, valid `user_uploaded` with 1–3 products, missing products, too many products, path traversal, invalid literal, model-without-products, and the `auto`-mode-keeps-cached-product-paths scenario. All tests use `VideoParams(...)` directly, no LLM/network mocks needed. Reference: [contracts/visuals-mode-wire-shape.md](contracts/visuals-mode-wire-shape.md) §"Test coverage (planned)".

---

## Phase 3: User Story 1 — Single product image, no model (Priority: P1) 🎯 MVP

**Story goal**: A creator picks "Use my own assets," uploads 1–3 product photos (no model), writes a script, and the resulting video uses ONLY those photos as B-roll. ZERO Pexels frames.

**Independent test**: Upload 3 product images → generate → `jq '.asset_audit'` of the resulting `script.json` shows `visuals_mode: "user_uploaded"`, `auto_pexels_used: false`, `pexels_clip_count: 0`, and `product_assets[]` matching the upload order. Visual playback confirms only uploaded images appear (with subtle zoom/pan).

### Backend — image upload endpoint (US1)

- [X] T005 [P] [US1] Write IU-1..IU-10 image-upload tests in `test/controllers/test_image_upload.py` (new file). Use FastAPI `TestClient` with multipart fixtures. Cover happy path, PNG transparency, oversize, unsupported MIME, corrupt JPEG, low-resolution warning, degenerate dimensions, zip-bomb, missing role field, and SHA-256 hash assertion. Reference: [contracts/image-upload-endpoint.md](contracts/image-upload-endpoint.md) §"Test coverage (planned)".

- [X] T006 [US1] Implement `POST /api/v1/uploads/image` in [app/controllers/v1/uploads.py](../../app/controllers/v1/uploads.py). Accept multipart `file` + `role` (`"model"|"product"`). Pipeline: validate (reuse `_validate_upload`), write original to `storage/uploads/<uuid>.<ext>`, run `Image.open(...).verify()` round-trip, handle EXIF transpose, compute SHA-256 of original bytes, center-crop to 9:16 (target 1080×1920 if source ≥ 1080 longest side, else proportional), write `storage/uploads/<uuid>.cropped.jpg` (JPEG q=88, sRGB, EXIF stripped). Return JSON per [contracts/image-upload-endpoint.md](contracts/image-upload-endpoint.md) §Response. Surface `low_resolution` warning when longest side < 720 px. Atomic cleanup (delete original + cropped) on any post-write failure.

- [X] T007 [US1] Verify T005 tests pass against the T006 implementation. Fix until 10/10 green.

### Backend — material.py dispatch + Ken Burns (US1)

- [X] T008 [P] [US1] Write MD-1..MD-10 dispatch tests in `test/services/test_uploaded_visuals.py` (new file). Mock MoviePy `ImageClip` and `write_videofile` so tests stay offline. Cover: sidecar absent → legacy path; sidecar with `auto` → still legacy; sidecar with `user_uploaded` + 1 product → 1 clip path returned; bookend variant (with model) deferred to US2 phase. Include audit-log shape assertions (load `script.json`, check `asset_audit.visuals_mode`, content_hashes). Reference: [contracts/material-py-dispatch.md](contracts/material-py-dispatch.md) §"Test coverage (planned)".

- [X] T009 [US1] Implement `_read_visuals_sidecar(task_id)` and the dispatch short-circuit at the top of `download_videos` in [app/services/material.py](../../app/services/material.py). When sidecar exists with `visuals_mode == "user_uploaded"`, route to `_build_clips_from_uploads`; otherwise fall through to existing Pexels code. Reference: [contracts/material-py-dispatch.md](contracts/material-py-dispatch.md).

- [X] T010 [US1] Implement `_make_kenburns_clip(image_path, duration, output_path, seed)` in [app/services/material.py](../../app/services/material.py) per [research.md R3](research.md#r3--ken-burns-motion-in-moviepy). Use seeded `random` so identical input → identical output. MoviePy chain: `ImageClip → resize(lambda t: ...) → set_position(lambda t: ...) → set_duration(duration) → CompositeVideoClip` at 9:16 target → `write_videofile(output_path, codec="libx264", fps=30, preset="medium", logger=None)`.

- [X] T011 [US1] Implement `_build_clips_from_uploads(task_id, model_path, product_paths, audio_duration, video_aspect)` in [app/services/material.py](../../app/services/material.py). Compute per-clip duration as `max(2.0, audio_duration / n_clips)` per FR-014/016. For US1 (no model), order is `[product_clips...]`. Write each clip to `storage/tasks/<task_id>/uploaded-<idx>.mp4`. Use SHA-256-derived seed per image for reproducibility.

- [X] T012 [US1] Implement audit-log writer in [app/services/material.py](../../app/services/material.py). Both branches write `asset_audit` to `storage/tasks/<task_id>/script.json` via atomic-rewrite (`tempfile.NamedTemporaryFile` + `os.replace`). Auto branch emits `{visuals_mode: "auto", auto_pexels_used: true, pexels_clip_count: <n>, model_asset: null, product_assets: []}` after Pexels download completes. User-uploaded branch emits the full shape per [data-model.md §3](data-model.md#3-asset-audit-log-per-task-json) including `content_hash`, `kenburns_clip_path`, `screen_time_seconds`, `placement` (US1: each product gets `"middle-N"`).

### Backend — sidecar writer in video controller (US1)

- [X] T013 [US1] In [app/controllers/v1/video.py](../../app/controllers/v1/video.py)'s `create_task` function (around line 127, after `task_id = utils.get_uuid()` and before `task_manager.add_task(...)`), add a sidecar-write block: when `body.visuals_mode == "user_uploaded"`, write `storage/tasks/<task_id>/visuals.json` containing `{visuals_mode, uploaded_model_path, uploaded_product_paths}` before dispatch. Verify each path exists on disk before writing; on missing-file return HTTP 400 with `{"error_code": "asset_not_found", "missing_path": "..."}`. Use `utils.task_dir(task_id, create=True)` to ensure the directory exists.

- [X] T014 [US1] Run full backend test suite: `pytest test/services/test_visuals_wire_shape.py test/services/test_uploaded_visuals.py test/controllers/test_image_upload.py -v`. Confirm 30/30 green. Fix any failures before proceeding to frontend.

### Frontend — helpers + tests (US1)

- [X] T015 [P] [US1] Write WV-1..WV-10 Vitest tests in `visualai-frontend/tests/visuals-mode.test.ts` (new file). Cover `PRISTINE_VISUALS`, `isPristineVisuals`, `visualsStateToParams` for all branches (auto with cached uploads → drops them; user_uploaded with no model → no `uploaded_model_path` key; with model → both keys), `canSubmitVisuals` thresholds, and the round-trip mode-switch retention. No component rendering — pure helper tests. Reference: [contracts/wizard-visuals-selector.md](contracts/wizard-visuals-selector.md) §"Test coverage".

- [X] T016 [P] [US1] Implement `visualai-frontend/src/lib/visuals-mode.ts` (new file) with the exact type definitions and helpers from [data-model.md §5](data-model.md#5-frontend-wizard-state-typescript) and [contracts/wizard-visuals-selector.md](contracts/wizard-visuals-selector.md) §"Helper module". Export `VisualsMode`, `UploadedAsset`, `WizardVisualsState`, `VisualsParams`, `PRISTINE_VISUALS`, `isPristineVisuals`, `visualsStateToParams`, `canSubmitVisuals`.

### Frontend — UI components (US1)

- [X] T017 [P] [US1] Implement `visualai-frontend/src/components/wizard/upload-slot-grid.tsx` (new file). Render one Model slot + three Product slots. Each slot supports drag-and-drop, click-to-select, progress bar (XHR), thumbnail preview, remove × button, retry on failure. Accept `image/jpeg,image/png,image/webp`. Pre-upload size guard at 30 MB (browser cap) and MIME extension check. POST to `/api/upload-image` and update parent state with the returned `UploadedAsset` on success. Use Tailwind styling consistent with existing wizard components.

- [X] T018 [P] [US1] Implement `visualai-frontend/src/components/wizard/visuals-selector.tsx` (new file). Composes a `<PillRow>` (reuse spec 013's component) with `auto` / `user_uploaded` options + the `<UploadSlotGrid>` from T017 (shown only when `mode === "user_uploaded"`). Accepts `state: WizardVisualsState` and `onChange` props per [contracts/wizard-visuals-selector.md](contracts/wizard-visuals-selector.md) §"UI component".

- [X] T019 [US1] Wire `<VisualsSelector>` into [visualai-frontend/src/app/modes/short-video/page.tsx](../../../visualai-frontend/src/app/modes/short-video/page.tsx) inside the Script & Voice step, between the existing script-mode pills (spec 013) and the music selector (spec 010). Add `visualsState: WizardVisualsState` to component state initialized from `PRISTINE_VISUALS`. Update `submit()` to call `visualsStateToParams(visualsState)` and merge the result into the request body. Update Generate-button enable logic to also require `canSubmitVisuals(visualsState)`.

### Frontend — proxies (US1)

- [X] T020 [P] [US1] Implement `visualai-frontend/src/app/api/upload-image/route.ts` (new file). Thin multipart proxy to MPT `POST /api/v1/uploads/image`. Forward FormData unchanged via `fetch(..., { method: "POST", body: form })`. Return MPT response status + JSON. Per [contracts/wizard-visuals-selector.md](contracts/wizard-visuals-selector.md) §"Frontend route".

- [X] T021 [US1] Extend [visualai-frontend/src/app/api/generate/route.ts](../../../visualai-frontend/src/app/api/generate/route.ts) to pass through `visuals_mode`, `uploaded_model_path`, and `uploaded_product_paths`. Insert the mapping block from [contracts/visuals-mode-wire-shape.md](contracts/visuals-mode-wire-shape.md) §"Wire shape" after the existing spec 013 `script_mode` pass-through. Validate that `uploaded_product_paths` is an array of strings.

### US1 verification

- [X] T022 [US1] Run full frontend test suite: `cd visualai-frontend && pnpm test visuals-mode`. Confirm 10/10 green.

- [~] T023 [US1] Manual smoke test (quickstart Parts 1 + 2): pristine-state regression check + single-product render. Verify `script.json#asset_audit.auto_pexels_used === false` for the user_uploaded render. Reference: [quickstart.md](quickstart.md) §"Part 1" and §"Part 2".

---

## Phase 4: User Story 2 — Model image bookend (Priority: P1)

**Story goal**: Add a model image that opens and closes the video; products play sequentially in the middle.

**Independent test**: Upload 1 model + 3 products → generate → final video shows model first (3–5s), products sequentially, model again (2–4s). Audit log records `model_asset.placement === "opening+closing"` and `product_assets[i].placement === "middle-{i+1}"`.

- [X] T024 [P] [US2] Add MD-bookend tests to `test/services/test_uploaded_visuals.py`: input = 1 model + 3 products → output is 5 clips in order `[model, p1, p2, p3, model]`; audit log placements correctly assigned; per-clip duration calculation handles `n_clips = product_count + 2` correctly when model is present.

- [X] T025 [US2] Update `_build_clips_from_uploads` in [app/services/material.py](../../app/services/material.py) to handle the model bookend: when `model_path` is non-null, prepend AND append `_make_kenburns_clip(model_path, ...)` to the product clips list. The model clip is generated ONCE and the same file is referenced for both bookends in the audit log (deduplicate the clip file, but `screen_time_seconds` reflects the sum of opening + closing durations). Update audit-log writer (T012) to record `model_asset.placement = "opening+closing"`.

- [X] T026 [P] [US2] Update `<UploadSlotGrid>` in [visualai-frontend/src/components/wizard/upload-slot-grid.tsx](../../../visualai-frontend/src/components/wizard/upload-slot-grid.tsx) to visually distinguish the Model slot from Product slots (e.g., wider slot, "Model image (optional)" label, icon). Add a tooltip explaining the bookend behavior: "Model image opens and closes your video."

- [~] T027 [US2] Manual smoke test (quickstart Part 3): 1 model + 3 products render. Verify visual sequence and audit log placements. Reference: [quickstart.md](quickstart.md) §"Part 3".

---

## Phase 5: User Story 3 — Mode switching mid-session (Priority: P2)

**Story goal**: User can toggle between Auto and My-assets within an open wizard session without losing uploaded assets or script/voice state.

**Independent test**: Start in My-assets, upload 3 products → toggle to Auto → toggle back to My-assets → uploads still visible in the slot grid → generate → render uses uploads.

- [~] T028 [P] [US3] Add WV-roundtrip test to `visualai-frontend/tests/visuals-mode.test.ts`: state transitions `pristine → user_uploaded → upload assets → auto → user_uploaded` end with the uploaded assets still in `productAssets[]`. `visualsStateToParams` returns `{visuals_mode: "auto"}` while in auto mode (drops uploads); returns full shape with uploads when back in user_uploaded.

- [X] T029 [US3] Verify state-preservation behavior in [visualai-frontend/src/app/modes/short-video/page.tsx](../../../visualai-frontend/src/app/modes/short-video/page.tsx): `<VisualsSelector>` is sibling state to the script editor and music selector, NOT child state. Mode toggles in any of the three selectors must not reset the others. Specifically test that toggling visuals does not clear the script-mode pill or music-track field, and vice versa.

- [~] T030 [US3] Manual smoke test (quickstart Part 4): mode-switch round-trip. Reference: [quickstart.md](quickstart.md) §"Part 4".

---

## Phase 6: Polish & cross-cutting

- [~] T031 [P] Manual smoke test (quickstart Part 5): validation errors — empty submit, .tiff rejection, oversize, low-res warning. Reference: [quickstart.md](quickstart.md) §"Part 5".

- [~] T032 [P] Manual smoke test (quickstart Part 6): backward-compatibility curl test simulating a legacy MPT request without `visuals_mode`. Reference: [quickstart.md](quickstart.md) §"Part 6".

- [~] T033 [P] Run quickstart Part 7 SC-001 invariant audit shell loop across `storage/tasks/`. Confirm zero "FAIL" lines. Reference: [quickstart.md](quickstart.md) §"Part 7".

- [~] T034 Update [STEP1_DEBT.md](../../STEP1_DEBT.md) cross-references: append a row for spec 006 documenting the touched files (`schema.py` + `material.py` + `uploads.py` + `video.py` controller) and the constitution-debt status (PASS-with-debt for I + III, PASS for II + IV + V). Note that debt #5 line count is unchanged (sidecar pattern preserved Q3's "no `task.py` edit" guarantee).

- [~] T035 Open PR for spec 006 against `main`. Title: `feat(006): user-uploaded model & product assets — Visuals selector for Mode 2`. Body must include: summary, Layer 3 + Layer 1 change list, constitution check (recap from plan.md), test plan checklist, and Jira Epic link (NEX-377 per existing spec 006 PR #6). Reference [PR #9](https://github.com/nexcognit-com/visualai-rendering-engine/pull/9) (spec 013) as the body template.

---

## Dependencies

```text
Phase 1 (Setup)            → Phase 2 (Foundational)
Phase 2 (Foundational)     → Phase 3 (US1)
Phase 3 (US1) — backend    → Phase 3 (US1) — frontend
Phase 3 (US1)              → Phase 4 (US2)
Phase 3 (US1) — frontend   → Phase 5 (US3)
Phases 3+4+5               → Phase 6 (Polish)
```

US1 frontend tasks (T015–T021) depend on US1 backend (T005–T014) being complete enough to receive uploads. The `cd visualai-frontend && pnpm test` cycle is independent once helper module + component code is written.

US2 backend (T024–T025) is the only US2 path needing backend work. Frontend (T026) is purely cosmetic and can land in parallel with backend.

US3 is essentially a verification + 1-test story — it's small because the React state-preservation pattern is a free side-effect of the way `<VisualsSelector>` is integrated in T019 (sibling state, not child).

## Parallel-execution opportunities

Within Phase 3 (US1):
- T005 + T008 + T015 can be written in parallel (three different test files, no implementation yet to break)
- T016 + T017 + T020 can be written in parallel (three different frontend files)

Within Phase 6 (Polish):
- T031 + T032 + T033 are all read-only manual checks → can run in parallel terminals

## Implementation strategy

**MVP scope = US1 only** (T001–T023). The Cortex41 Pexels-mismatch problem that drove this feature is fully resolved as soon as a creator can render a Mode 2 video using their own product photos with no model. US2 (model bookend) and US3 (mode switching) are additive polish on the same data path.

**Recommended landing order**:
1. Setup + Foundational (T001–T004) — schema + tests — ~30 min.
2. US1 backend (T005–T014) — endpoint + dispatch + audit + sidecar — ~3–4 hours.
3. US1 frontend (T015–T023) — helper + components + page wiring + smoke test — ~3–4 hours.
4. US2 (T024–T027) — model bookend + UI polish — ~1 hour.
5. US3 (T028–T030) — verification + 1 test — ~30 min.
6. Polish (T031–T035) — quickstart sweeps + debt tracker + PR — ~1 hour.

Total: ~9–10 hours across two repos.

## Validation checklist

- [x] Every task has a checkbox + sequential ID + clear file path.
- [x] User-story tasks carry `[US1]`, `[US2]`, or `[US3]` labels; setup/foundational/polish tasks do not.
- [x] Parallel-safe tasks marked `[P]`.
- [x] Each user story has its own phase with an independent-test criterion at the top.
- [x] Foundational tasks (T003 + T004) gate every user-story phase.
- [x] Tests precede implementation within each story (T005 before T006; T008 before T009–T012; T015 before T016).
- [x] No task depends on a file the previous task hasn't touched (verified by re-reading file paths in the dependencies).

---

## Phase 7: Hybrid Mode Addition (Clarifications 2026-05-03)

**Story goal**: A creator picks `Hybrid` in the Visuals selector → uploads 0–1 model + 1–3 product images → the rendered video alternates `[stock_setting, user_image, stock_setting, user_image, …, stock_closing]` with stock clips fetched from Pexels + Pixabay using a two-pass setting-tag prompt. Generic "computer vision software" search-term failures are gone; the renderer always finds setting footage that contextualises the product.

**Independent test**: Render a Cortex41-style script ("AI-powered facility management for clinics") in `hybrid` mode with 1 product screenshot → resulting `script.json#asset_audit.setting_tag` is `"healthcare"`, `stock_queries` contains clinic/healthcare-themed terms, the final video alternates user-image segments with clinic stock footage in the FR-022 pattern.

### Backend — schema + LLM (foundational for hybrid)

- [X] T036 Extend `visuals_mode` Literal in [app/models/schema.py](../../app/models/schema.py) to include `"hybrid"`. Update `_validate_visuals` to accept `hybrid` with the same product-paths rule as `user_uploaded` (1–3 required, model optional). Add VW-11 / VW-12 cases to `test/services/test_visuals_wire_shape.py` covering valid hybrid inputs and that hybrid + zero products still raises `no_product_assets`.

- [X] T037 [P] Add tests for `extract_setting_tag` and `expand_setting_to_queries` in `test/services/test_setting_terms.py` (new file). Mock `llm._generate_response` with controlled returns so tests are offline. Coverage:
    - ST-1: `extract_setting_tag("AI-powered patient triage for clinics")` → `"healthcare"`
    - ST-2: `extract_setting_tag("Defect detection on the assembly line")` → `"manufacturing"`
    - ST-3: empty/garbled LLM response → falls back to `"general"`
    - ST-4: LLM returns invalid tag (e.g., `"airspace"`) → falls back to `"general"`
    - ST-5: `expand_setting_to_queries("manufacturing")` → list of 5 strings; each is non-empty
    - ST-6: `expand_setting_to_queries("healthcare")` → 5 distinct queries
    - ST-7: `expand_setting_to_queries("general")` → office/lifestyle queries (people walking, business meeting, etc.)
    - ST-8: LLM returns malformed JSON for queries → falls back to a baked-in default list per tag
    - ST-9: `generate_setting_terms(script_text)` orchestrator returns `(setting_tag, queries[5])` tuple
    - ST-10: orchestrator handles LLM failure on either pass → returns `("general", general_queries[5])`

- [X] T038 Implement `extract_setting_tag(script_text: str) -> Literal[...]` in [app/services/llm.py](../../app/services/llm.py). Prompt instructs the LLM to choose exactly one of 11 tags (`manufacturing`, `healthcare`, `retail`, `office`, `logistics`, `hospitality`, `education`, `fitness`, `construction`, `agriculture`, `general`). Validate the returned string against the allowlist; fall back to `"general"` on invalid/empty.

- [X] T039 Implement `expand_setting_to_queries(setting_tag: str) -> list[str]` in [app/services/llm.py](../../app/services/llm.py). Prompt instructs the LLM to produce exactly 5 Pexels-friendly search queries scoped to the given setting. Parse JSON list from the response; on parse failure use a baked-in default-queries-per-tag map (each tag maps to 5 fallback queries inline in the file).

- [X] T040 Implement `generate_setting_terms(script_text: str) -> tuple[str, list[str]]` in [app/services/llm.py](../../app/services/llm.py). Wraps T038 + T039; returns `(setting_tag, queries)`. On any internal failure returns `("general", default_general_queries)`.

### Backend — material.py hybrid dispatch

- [X] T041 [P] Add MD-hybrid tests to `test/services/test_uploaded_visuals.py`:
    - MD-11: sidecar `mode=hybrid` + 1 product (no model) → renderer returns interleaved `[stock_clip, user_clip_1, stock_clip, stock_closing_clip]` (alternation with stock-open + stock-close).
    - MD-12: sidecar `mode=hybrid` + 1 model + 3 products → returns `[stock, model, stock, p1, stock, p2, stock, p3, stock_closing]`.
    - MD-13: Pexels + Pixabay both empty for tier-1 → tier-2 (`general` queries) fires; if also empty, fall back to user-only with `pexels_empty_fallback: true` in audit.
    - MD-14: `_search_stock_dual_source` queries both Pexels + Pixabay; dedupes by URL; preserves first-found order.
    - MD-15: audit log for hybrid runs records `setting_tag`, `stock_queries`, per-stock-clip `provider` + `query`, no `model_asset.placement="opening+closing"` (model is at slot 2 in hybrid per FR-022).

- [X] T042 Implement `_search_stock_dual_source(query, video_aspect, max_clip_duration)` in [app/services/material.py](../../app/services/material.py). Calls `search_videos_pexels` and `search_videos_pixabay` (both already present), merges results by URL, returns ordered list. No new dependency.

- [X] T043 Implement `_build_clips_hybrid(task_id, model_path, product_paths, audio_duration, video_aspect, setting_tag, queries)` in [app/services/material.py](../../app/services/material.py). Implements the alternation pattern from FR-022:
    1. Compute `n_user_clips = len(product_paths) + (1 if model_path else 0)`.
    2. Compute `n_stock_clips = n_user_clips + 1` (one extra for the closing position).
    3. For each of the `n_stock_clips`: round-robin through `queries`, call `_search_stock_dual_source`, download via `save_video`, take first available. If a query returns nothing, advance to next; track empties.
    4. Two-tier retry: if total stock fetched < n_stock_clips after first pass, retry with `general` queries; if still short, fall back to all-user-images and write `pexels_empty_fallback: true`.
    5. Render user clips via the existing `_render_one` Ken Burns helper.
    6. Build the interleaved list: `[stock_0, user_0, stock_1, user_1, …, stock_n]` where `user_0` is `model` when present, then products in order.
    7. Write `asset_audit` per FR-025 (setting_tag + stock_queries + per-clip provider/query + fallback flag).

- [X] T044 Wire hybrid dispatch into `download_videos` in [app/services/material.py](../../app/services/material.py). The existing sidecar branch checks `visuals_mode == "user_uploaded"` → route to `_build_clips_from_uploads`. Add a parallel check for `visuals_mode == "hybrid"` → route to `_build_clips_hybrid`. Read `setting_tag` and `stock_queries` from the sidecar (the controller writes them pre-dispatch via T046).

### Backend — controller sidecar extension

- [X] T045 [P] Add a controller test in `test/controllers/test_image_upload.py` (or new `test_video_controller_sidecar.py`) verifying that POST `/api/v1/videos` with `visuals_mode="hybrid"` writes `storage/tasks/<task_id>/visuals.json` containing `visuals_mode: "hybrid"`, `setting_tag`, `stock_queries`, and the user paths. Mock `llm.generate_setting_terms` to return a controlled tuple so the test is offline.

- [X] T046 Update `_maybe_write_visuals_sidecar` in [app/controllers/v1/video.py](../../app/controllers/v1/video.py): when `visuals_mode == "hybrid"`, call `llm.generate_setting_terms(body.video_subject or body.video_script)` BEFORE writing the sidecar. Persist `setting_tag` + `stock_queries` into the sidecar JSON. The existing `user_uploaded` branch is unchanged.

### Backend — full sweep

- [X] T047 Run `pytest test/services/test_visuals_wire_shape.py test/services/test_setting_terms.py test/services/test_uploaded_visuals.py test/controllers/test_image_upload.py -v`. Confirm all green (target: 50+ tests).

### Frontend — hybrid mode wiring

- [X] T048 [P] Update [visualai-frontend/tests/visuals-mode.test.ts](../../../visualai-frontend/tests/visuals-mode.test.ts) with hybrid coverage: `visualsStateToParams({mode: "hybrid", ...})` emits `{visuals_mode: "hybrid", uploaded_product_paths: [...], uploaded_model_path?: ...}`; `canSubmitVisuals({mode: "hybrid"})` returns true with 1+ products, false with 0.

- [X] T049 Update [visualai-frontend/src/lib/visuals-mode.ts](../../../visualai-frontend/src/lib/visuals-mode.ts): extend `VisualsMode` type to `"auto" | "hybrid" | "user_uploaded"`. Update `visualsStateToParams` to handle hybrid (same shape as user_uploaded but with `visuals_mode: "hybrid"`). Update `canSubmitVisuals` to treat hybrid the same as user_uploaded (1–3 products required).

- [X] T050 Update `<VisualsSection>` in [visualai-frontend/src/app/modes/short-video/page.tsx](../../../visualai-frontend/src/app/modes/short-video/page.tsx): pill row goes from 2 to 3 options (`auto` / `hybrid` / `user_uploaded`). Hybrid shares the upload-slot grid behavior with user_uploaded. Update helper text per mode (auto: "Pexels stock — fast but generic"; hybrid: "Your assets mixed with relevant context footage"; user_uploaded: "Your images only").

- [X] T051 Update [visualai-frontend/src/app/api/generate/route.ts](../../../visualai-frontend/src/app/api/generate/route.ts) pass-through: accept `body.visuals_mode === "hybrid"` and forward `visuals_mode: "hybrid"` plus `uploaded_*_paths` to MPT. Existing `auto` and `user_uploaded` branches unchanged.

### Phase 7 verification

- [X] T052 Run full frontend test suite: `cd visualai-frontend && pnpm vitest run`. Confirm visuals-mode tests still all pass with hybrid additions.

- [ ] T053 [~] Manual smoke (deferred to user): restart MPT, upload 1 product photo of a UI screenshot + write a Cortex41-style script, pick **Hybrid**, generate, verify the output alternates user UI with healthcare/clinic stock footage and `script.json#asset_audit.setting_tag === "healthcare"`.

