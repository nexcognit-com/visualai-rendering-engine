---

description: "Task list for Mode 3 — Long-Form Video Generator (16:9, 2-5 min)"
---

# Tasks: Mode 3 — Long-Form Video Generator (spec 016)

**Input**: Design documents from `/specs/016-long-form-video/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓ (3 files), quickstart.md ✓

**Tests**: Included — Constitution §Development Workflow requires `pytest test/` to pass and a smoke test for new mode code; contracts call out specific test files.

**Organization**: Tasks are grouped by user story (US1=P1 MVP, US2=P2, US3=P2, US4=P3) so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependencies on incomplete tasks
- **[Story]**: US1/US2/US3/US4 — maps task back to a user story (Setup / Foundational / Polish phases have no story label)
- File paths are absolute relative to each repo's root: `mpt:` = MoneyPrinterTurbo (Layer 3, this repo), `l2:` = visualai-orchestration (Layer 2), `l1:` = visualai-frontend (Layer 1)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify scaffolding shipped by spec 015 (PR-A) is usable for Mode 3, and prepare config defaults.

- [ ] T001 Verify Layer 3's `app/services/modes/__init__.py` registry skeleton exists and exposes a `register(mode_config)` API (shipped by spec 015 PR-A); if missing, file an issue against PR-A before continuing.
- [ ] T002 Verify Layer 2 `app/services/pre_signer.py` is reachable and `sign_url(tenant_id, filename)` works for `lf_<id>/final-1.mp4` paths (same convention spec 015's product shoots use).
- [ ] T003 [P] Confirm Layer 1 `.env.local` has `NEXT_PUBLIC_LAYER2_URL=http://127.0.0.1:8089` (from spec 015 — already set per memory).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core surfaces that ALL user stories depend on. No US task can start until Phase 2 is green.

**⚠️ CRITICAL**: Run T004–T010 before any US-labelled task.

- [ ] T004 Extend `VideoParams.mode` Literal in `mpt:app/models/schema.py` to include `"long"` alongside existing `"short"` and `"faceless"` values.
- [ ] T005 Create the long-form mode registry entry at `mpt:app/services/modes/long_form.py` with the `ModeConfig` shown in `contracts/layer3-render-contract.md` (aspect 16:9, target res 1920×1080, durations {120,180,240,300}, default 180, wpm 150, subtitle band y=0.80, segment count range 8-25, music volume -18dB, script template HOOK_BODY_SUMMARY).
- [ ] T006 [P] Create the `LongFormGeneration` Pydantic model at `l2:app/models/long_form.py` matching `data-model.md` (id, tenant_id, user_id, status enum, source_type enum, source_text, target_duration_seconds, actual_duration_seconds, voice_id, music_id, script_text, output_video_url, subtitle_band_y_pct, latency_ms, cost_estimate_usd, error_code, error_message, created_at, completed_at).
- [ ] T007 [P] Create the JSON-file persistence layer at `l2:app/services/long_form_store.py` mirroring `product_shoot_store.py` from spec 015: `_STORAGE_ROOT = Path("storage/tasks")`, lazy `_ensure_loaded`, `put`, `get` with URL re-mint, `list_for_tenant` with newest-first + viewable-only filter (≥100KB threshold for `final-1.mp4`), `clear` test helper.
- [ ] T008 [P] Add a smoke test at `mpt:test/services/modes/test_long_form.py` covering the four assertions in `contracts/layer3-render-contract.md` (aspect, durations, subtitle band, generate_long_form_script returns hook/body/summary keys with mocked LLM).
- [ ] T009 Implement `generate_long_form_script(input_text, source_type, target_duration_seconds) -> dict` in `mpt:app/services/llm.py` — additive helper next to existing `generate_marketing_script`. Returns `{"hook": str, "body": list[str], "summary": str, "full_text": str}`. Word-budget = `target_duration_seconds * 2.5`.
- [ ] T010 Add a unit test at `mpt:test/services/test_llm_long_form.py` for `generate_long_form_script` — mocks the LLM and asserts the structured return shape + word budget enforcement.

**Checkpoint**: Layer 3 mode registry + script helper green; Layer 2 model + store green. User-story phases can begin.

---

## Phase 3: User Story 1 — Topic prompt → 3-min explainer (Priority: P1) 🎯 MVP

**Goal**: From a topic prompt, end-to-end produce a downloadable 16:9 MP4 within ~3–5 minutes, surfaced in My Assets.

**Independent Test**: Submit `{source_type: "topic", source_text: "How AI is changing logistics in 2026", target_duration_seconds: 180, voice_id: "en-US-AvaMultilingualNeural", music_id: null}` to Layer 2; receive a `complete` record with a pre-signed `output_video_url`; download → playback shows 16:9 1080p, 2:45–3:15 duration, lower-third subtitles.

### Tests for User Story 1

- [ ] T011 [P] [US1] Contract test for `POST /api/v1/long-form-videos` happy path at `l2:tests/routes/test_long_form_videos.py::test_lf1_topic_returns_complete_record` — uses `respx` to mock OpenAI (script gen) + Layer 3 (`/api/v1/videos`) + Layer 2.5 visuals; asserts 200 OK + record shape + pre-signed URL format.
- [ ] T012 [P] [US1] Validation tests in `l2:tests/routes/test_long_form_videos.py` for `source_too_long` (501-char topic), `source_too_short` (empty), `invalid_target_duration` (90s), `unknown_voice_id`, `unknown_music_id`.
- [ ] T013 [P] [US1] Auth tests at `l2:tests/routes/test_long_form_videos.py::test_lf_no_auth_returns_401` and `::test_lf_wrong_bearer_returns_401`.

### Implementation for User Story 1

- [ ] T014 [US1] Create `l2:app/routes/long_form_videos.py` with `POST /api/v1/long-form-videos`. Validates input (FR-014, FR-003, FR-004); generates `lf_<hex>` id; persists `running` record; calls `generate_long_form_script` via Layer 3 OR generates script via direct OpenAI call (research D-1) — pick the latter for simpler v1; awaits voice synthesis + B-roll fetch + Layer 3 render; persists `complete` record with pre-signed URL.
- [ ] T015 [US1] Wire Layer 2's outbound call to Layer 3 — build `VideoParams` payload with `mode="long"`, `video_aspect="16:9"`, `subtitle_position="bottom"`, full `script`, voice id, music id, `video_materials` list (pre-signed B-roll URLs from Layer 2.5). POST to `mpt:/api/v1/videos` and await the assembled MP4.
- [ ] T016 [US1] Register `long_form_videos.router` in `l2:app/main.py` (mirrors `app.include_router(product_shoots.router)` from spec 015).
- [ ] T017 [P] [US1] Add the Long-Form Video card to `l1:src/app/page.tsx` dashboard grid — title "Long-Form Video", subtitle "16:9 explainer for YouTube · 2-5 min", lucide `monitor-play` icon, click target `/modes/long-form/`.
- [ ] T018 [US1] Build the 3-step wizard at `l1:src/app/modes/long-form/page.tsx` — Step 1 input (3 pills: Topic / URL / Script — only Topic functional in this US), Step 2 config (duration radios, voice picker, music picker), Step 3 progress + result. Reuse Mode 1's lightbox / download UX patterns.
- [ ] T019 [P] [US1] Create the API proxy at `l1:src/app/api/long-form-videos/route.ts` mirroring `l1:src/app/api/product-shoots/route.ts` from spec 015 — POST forwards JSON to Layer 2 with bearer header injected from server-side env.
- [ ] T020 [US1] Wire the wizard's Generate button → call `/api/long-form-videos`, render fixed-stage progress animation (4 stages), display inline `<video controls>` on completion with HTML5 download attribute (filename `long-form-{slug}-{timestamp}.mp4`).
- [ ] T021 [US1] Add structured logging in `l2:app/routes/long_form_videos.py` per Constitution §Observability — every log line includes `tenant_id`, `user_id`, `generation_id`, `source_type`, plus stage transitions ("script_generated", "voice_synthesized", "visuals_fetched", "render_dispatched", "render_complete").
- [ ] T022 [US1] Run quickstart.md US1 walkthrough end-to-end on localhost; verify SC-001 (≤5 min wall-clock), SC-002 (±15s duration), SC-003 (lower-third subtitles), SC-005 (≤$0.50 cost).

**Checkpoint**: US1 fully functional. Stop and demo MVP. Other stories can now branch off in parallel.

---

## Phase 4: User Story 2 — URL source type (Priority: P2)

**Goal**: User pastes a product URL → script grounded in scraped content → 16:9 explainer.

**Independent Test**: Submit `{source_type: "url", source_text: "https://example.com/product", target_duration_seconds: 240, ...}`; assert the generated `script_text` references facts from the scraped page (the test mocks the spec-012 scraper to return a known string).

### Tests for User Story 2

- [ ] T023 [P] [US2] Test `l2:tests/routes/test_long_form_videos.py::test_lf_url_source_grounded_in_scrape` — mocks `/api/scrape-url` (Layer 1, spec 012) to return `"Product X is a smart home device that ..."`; asserts the LLM prompt sent to script-gen includes that string; asserts response 200 OK.
- [ ] T024 [P] [US2] Test `l2:tests/routes/test_long_form_videos.py::test_lf_url_unreachable_returns_502_url_unreachable` — mocks scraper returning 5xx; asserts response 502 with `error_code="url_unreachable"`.
- [ ] T025 [P] [US2] Test `l2:tests/routes/test_long_form_videos.py::test_lf_invalid_url_returns_422` — submits `source_text="not a url"` with `source_type="url"`; asserts 422 `error_code="invalid_url"`.

### Implementation for User Story 2

- [ ] T026 [US2] In `l2:app/routes/long_form_videos.py`, branch on `source_type`. For `url`, call Layer 1's `/api/scrape-url` (spec 012); pass cleaned text into `generate_long_form_script` with `source_type="url"`.
- [ ] T027 [US2] Add URL regex validation in the request validator (`^https?://` minimum); on miss, return 422 `invalid_url` with the exact body from `contracts/layer2-long-form-api.md`.
- [ ] T028 [US2] Map scraper failures (timeout, 5xx, robots.txt block) into `502 url_unreachable` with the user-facing detail; preserve the underlying scraper error code in logs.
- [ ] T029 [P] [US2] Wire the URL pill in the wizard at `l1:src/app/modes/long-form/page.tsx`; add inline URL validation; on focus-out, optionally call `/api/scrape-url` to preview the page title in a small "Detected: <title>" hint.
- [ ] T030 [US2] In the wizard's error-handling path, on `error_code === "url_unreachable"` show a "Try as a topic prompt instead" button that pre-fills Step 1's Topic pill with the URL's title (FR-016).

**Checkpoint**: US1 + US2 both ship. Test together with one of each in `My Assets`.

---

## Phase 5: User Story 3 — My Assets surfacing (Priority: P2)

**Goal**: Long-form videos appear in My Assets alongside Mode 1 product shoots and Mode 2/5 short videos.

**Independent Test**: Generate one long-form video; navigate to `/assets`; assert a new card with a 16:9 thumbnail appears at the top; click → inline `<video>` plays.

### Tests for User Story 3

- [ ] T031 [P] [US3] Test `l2:tests/routes/test_long_form_videos.py::test_lf_list_returns_all_for_tenant_newest_first` — mirrors spec 015's `test_ps11_list_returns_all_for_tenant_newest_first` pattern.
- [ ] T032 [P] [US3] Test `l2:tests/routes/test_long_form_videos.py::test_lf_list_filters_records_below_100kb` — confirms records whose `final-1.mp4` is missing or under 100KB are filtered out (mirrors spec 015's `_MIN_VALID_SHOT_BYTES` filter).
- [ ] T033 [P] [US3] Test `l2:tests/routes/test_long_form_videos.py::test_lf_get_unknown_id_returns_404` and `::test_lf_get_returns_record_with_fresh_url`.

### Implementation for User Story 3

- [ ] T034 [US3] Implement `GET /api/v1/long-form-videos` in `l2:app/routes/long_form_videos.py` — calls `long_form_store.list_for_tenant(demo_tenant_id)`; returns the filtered list per `contracts/layer2-long-form-api.md`.
- [ ] T035 [US3] Implement `GET /api/v1/long-form-videos/{id}` — calls `long_form_store.get(record_id)`; 404 if missing per the contract.
- [ ] T036 [US3] In `l2:app/services/long_form_store.py::list_for_tenant`, ensure the 100KB minimum file-size filter is applied identically to spec 015's `_MIN_VALID_SHOT_BYTES = 20_000` pattern (use `_MIN_VALID_VIDEO_BYTES = 100_000` for long-form's much larger files).
- [ ] T037 [P] [US3] Add the `LongFormCard` component variant in `l1:src/app/assets/page.tsx` — 16:9 thumbnail via `<video preload="metadata">`, "Long-form · {duration_seconds}s" badge, click → opens an inline preview modal with the full video.
- [ ] T038 [US3] Extend the My Assets fetch in `l1:src/app/assets/page.tsx` to include `/api/long-form-videos` (parallel with `/api/history` and `/api/product-shoots`); merge into the heterogeneous grid sorted by `created_at DESC`.
- [ ] T039 [P] [US3] Add the GET-list proxy at `l1:src/app/api/long-form-videos/route.ts` (extend the file from T019).

**Checkpoint**: My Assets surfaces all three asset types correctly.

---

## Phase 6: User Story 4 — Pre-written script (Priority: P3)

**Goal**: Power user pastes a polished script; system skips script-generation and renders narration verbatim.

**Independent Test**: Submit `{source_type: "script", source_text: "<400-word script>", target_duration_seconds: 180, ...}`; assert response `script_text` matches input verbatim (only minor punctuation normalization allowed) and the produced video's narration matches.

### Tests for User Story 4

- [ ] T040 [P] [US4] Test `l2:tests/routes/test_long_form_videos.py::test_lf_script_source_no_llm_call` — mocks LLM endpoints to return errors; asserts the route succeeds without invoking script-gen LLM (verified via respx call counts).
- [ ] T041 [P] [US4] Test `l2:tests/routes/test_long_form_videos.py::test_lf_script_word_count_mismatch_warns` — submits 50-word script with `target_duration_seconds=300`; asserts response includes `warning_code: "duration_word_count_mismatch"` (or 422 if hard-rejected per implementation choice).

### Implementation for User Story 4

- [ ] T042 [US4] In `l2:app/routes/long_form_videos.py`, when `source_type == "script"`, set `script_text = source_text.strip()` directly and SKIP the call to `generate_long_form_script`. Persist `script_text` to the record before invoking voice synthesis.
- [ ] T043 [US4] Add the word-count-vs-duration sanity check: warn (not error) when actual word count diverges from `target_duration_seconds * 2.5` by more than ±30%; surface as a non-blocking field on the response record (or a separate `warnings: [...]` array).
- [ ] T044 [P] [US4] Wire the "Pre-written script" pill in the wizard at `l1:src/app/modes/long-form/page.tsx`; add a word counter (current / 1500); disable Generate when empty or > 1500 words.
- [ ] T045 [US4] Surface the word-count-mismatch warning in the wizard's progress UI as an amber badge ("Heads up: your script is short for the chosen duration") that doesn't block generation.

**Checkpoint**: All four user stories ship. Mode 3 v1 complete.

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: Sweep things that affect multiple user stories.

- [ ] T046 [P] Update `mpt:CLAUDE.md` "Recent Changes" entry with spec 016's stack notes (already auto-updated by `update-agent-context.sh`; verify it's accurate).
- [ ] T047 [P] Add a Mode 3 row to `mpt:STEP1_DEBT.md` if/when spec 014 lands and burns the demo-tenant debt — link the row to the spec-014 PR (deferred until spec 014 is in flight; placeholder for tracking).
- [ ] T048 Run quickstart.md US2 walkthrough end-to-end with a real product URL (post-MVP smoke, validates the URL-flow against live spec-012 scraping).
- [ ] T049 Verify cost-estimate logging across all three source types — capture median across 5 generations per duration {120, 180, 240, 300} and confirm SC-005 ($0.50 median) holds.
- [ ] T050 [P] Update `mpt:specs/016-long-form-video/checklists/requirements.md` to mark every item passing post-implementation; add a final-iteration note with the date the implementation lands.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001–T003 — verify-only, can start immediately.
- **Foundational (Phase 2)**: T004–T010 — block all user-story phases. T004 → T005 (literal feeds the registry). T006 + T007 + T008 [P] in parallel. T009 → T010.
- **US1 (Phase 3)**: T011–T013 [P] in parallel; then T014 → T015 → T016. T017 + T019 [P] in parallel; then T018 → T020. T021 + T022 last.
- **US2 (Phase 4)**: T023–T025 [P] in parallel; then T026 → T027 → T028. T029 [P] alongside; T030 last.
- **US3 (Phase 5)**: T031–T033 [P] in parallel; then T034 + T035 + T036; then T037 + T038 + T039 [P].
- **US4 (Phase 6)**: T040 + T041 [P]; then T042 → T043; T044 [P]; T045 last.
- **Polish (Phase 7)**: depends on all desired user stories shipped.

### User Story Dependencies

- **US1 (P1)**: depends only on Foundational. MVP slice.
- **US2 (P2)**: depends on Foundational + US1's wizard scaffold (T018) for the URL pill. The Layer 2 url-source branch (T026–T028) can run in parallel with US3 backend work.
- **US3 (P2)**: depends on Foundational. Layer 2 + Layer 1 work can proceed in parallel with US2.
- **US4 (P3)**: depends on Foundational + US1's wizard scaffold. Backend script-skip branch (T042–T043) is small and can run in parallel with anything.

### Parallel Opportunities

- All `[P]` tasks within the same phase can run in parallel (different files, no shared state).
- Once Foundational completes, US1 / US2 / US3 / US4 can be worked on in parallel by different developers — only the wizard file (`long-form/page.tsx`) is a shared touch-point across US1/US2/US4 and needs sequential edits or explicit pill-by-pill PRs.

---

## Parallel Example: User Story 1

```bash
# Foundational tests + models in parallel:
Task: "T006 Create LongFormGeneration model in l2:app/models/long_form.py"
Task: "T007 Create JSON-file store in l2:app/services/long_form_store.py"
Task: "T008 Smoke test in mpt:test/services/modes/test_long_form.py"

# US1 contract tests in parallel:
Task: "T011 Happy-path contract test"
Task: "T012 Validation error tests"
Task: "T013 Auth tests"

# US1 frontend scaffolding in parallel:
Task: "T017 Dashboard card"
Task: "T019 API proxy route"
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 + Phase 2 → green.
2. Phase 3 (US1) → green; demo on localhost.
3. STOP, validate against the four SC metrics (SC-001/002/003/005).
4. If green, proceed to US2 / US3 / US4 in priority order.

### Incremental delivery

Each user-story phase ships an independently-demoable increment. After US1 the dashboard has Mode 3 working; after US3 it shows up in My Assets; US2 and US4 broaden the input modes; US4 can ship last as a power-user feature.

---

## Notes

- The Constitution requires every Layer 3 service log line to carry `tenant_id`, `user_id`, `generation_id`. T021 is load-bearing — don't skip.
- Spec 015's `product_shoot_store.py` is the reference pattern for T007 + T036; copy its disk-load + URL-refresh + size-filter behaviour exactly. Prevents the "in-memory store wiped on restart" trap we already paid once.
- T008 + T010 are the only constitution-required tests. Other tests (T011–T013, T023–T025, T031–T033, T040–T041) are insurance for SC verification and contract regressions.
- Mode 3 v1 ships against demo-tenant; T047 is the placeholder for spec 014's tenant rollup. Don't try to fix Principle III as part of this spec.
