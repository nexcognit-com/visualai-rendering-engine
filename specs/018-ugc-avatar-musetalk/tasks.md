---

description: "Task list for spec 018 — Mode 4 UGC Avatar Generator (MuseTalk lip-sync)"
---

# Tasks: Mode 4 — UGC Avatar Generator (MuseTalk lip-sync)

**Input**: Design documents from [`specs/018-ugc-avatar-musetalk/`](.)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: The constitution mandates `pytest test/` passes locally before any PR opens, and at least one smoke test for new mode code with mocked Layer 2 inputs (Constitution §Development Workflow). Test tasks below honour that minimum — they are NOT a TDD-style "write all tests first" pass.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. Three priorities — P1 (Auto-mode MVP) → P2 (Verbatim) → P3 (Polish). The MVP STOP point is end of Phase 3.

**Format**: `[ID] [P?] [Story] Description`

- `[P]`: Parallelizable — different files, no in-flight dependencies
- `[Story]`: Maps to user story (US1/US2/US3 from spec.md). Setup/Foundational/Polish phases have no story label.
- File paths reference the three repos: **L3** = `MoneyPrinterTurbo/`, **L2** = `visualai-orchestration/`, **L1** = `visualai-frontend/`.

> **Revision 2026-05-06**: Tasks were renumbered after `/speckit.analyze` surfaced 8 findings (none CRITICAL). All 8 are addressed in this revision. New tasks: T037–T039 (cancel option per F2/FR-010), T032–T033 (list-recent endpoints per F6/FR-014), T060 (perf benchmark per F4/SC-001). Modifications: T011 (aspect-ratio crop per F8), T031 (tightened from "decide later" per F6), T062 (My Assets surface verification per F7).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency wiring, and the constitutional amendment that unlocks Mode 4.

- [X] T001 Constitution amendment v1.1.0 → v1.2.0 in `MoneyPrinterTurbo/.specify/memory/constitution.md` — promote Mode 4 from "reserved" to "actively implemented" (mirror the v1.1.0 wording change for Modes 1+5); add Sync Impact Report block at top; bump version + Last Amended line. Ship as a separate `chore:` commit BEFORE any Mode 4 implementation lands.
- [X] T002 [P] Add `mediapipe>=0.10` to `MoneyPrinterTurbo/pyproject.toml` `dependencies = [...]` block; run `.venv/bin/pip install -e ".[dev]"` (or equivalent) and verify `import mediapipe` works.
- [X] T003 [P] **Pivoted 2026-05-06**: MuseTalk's repo has no `setup.py` / `pyproject.toml` — not pip-installable. Its `requirements.txt` pins `tensorflow==2.12.0` + `numpy==1.23.5` which conflict with L3's existing deps (faster-whisper, mediapipe, edge-tts). Replaced the `pip install git+` strategy with vendored-clone: `pyproject.toml` carries a documenting comment only; the actual clone + dep install happens in T005's `scripts/install_musetalk.sh`. T011's runtime `import` then targets `vendor/musetalk/musetalk/` directly.
- [X] T004 [P] Add new env var documentation in `MoneyPrinterTurbo/.env.example` for `LIP_SYNC_ENGINE` (default `mock` for dev safety; flip to `musetalk` on GPU hosts), `MUSETALK_MODEL_DIR`, `MUSETALK_DEVICE` (auto-detect cuda → mps → cpu), `LIP_SYNC_LOOP_SEAM_FADE_SECONDS`.
- [X] T005 [P] Created `MoneyPrinterTurbo/scripts/install_musetalk.sh` — combines T003's vendored-clone strategy with the weights download. Pins SHA `0a89dec45a`, installs curated runtime deps (torch, diffusers, librosa) excluding tensorflow conflict, downloads weights via huggingface-cli into `$MUSETALK_MODEL_DIR`, runs an import-time verification step. README-en.md gained a `(Optional) Mode 4` section pointing at the script.

**Checkpoint**: dependencies installable, env vars documented, constitutional gate cleared.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: L3 schema + lip-sync service + mode registry + selfie upload endpoint. Every user story below depends on this phase finishing.

**⚠️ CRITICAL**: No US1/US2/US3 work begins until this phase is done.

- [X] T006 Extend `VideoParams` in `MoneyPrinterTurbo/app/models/schema.py`: (a) add `"ugc_avatar"` to the `Mode` Literal type; (b) add `speaker_reference_path: Optional[str] = None`. Keep all existing fields untouched. Add inline comment referencing spec 018.
- [X] T007 Created `MoneyPrinterTurbo/app/services/lip_sync.py` with full public surface (`detect_face`, `extend_reference_to_duration`, `run`) + module-level config (`LIP_SYNC_ENGINE`, `MUSETALK_MODEL_DIR`, `MUSETALK_DEVICE`, `LIP_SYNC_LOOP_SEAM_FADE_SECONDS`). Module loads cleanly without torch installed.
- [X] T008 `detect_face()` — MediaPipe `FaceDetection` (model_selection=0 short-range), 30 evenly-sampled frames, area×proximity-to-center×confidence ranking, returns face_bbox + face_count + source dimensions. `no_face_detected` raised when confidence threshold not met.
- [X] T009 `extend_reference_to_duration()` — ping-pong filter chain `[0:v]reverse[rev{i}];[0:v][rev{i}]concat=n=2:v=1[pp{i}]` repeated `cycles_needed` times, then concat all `[pp{i}]` blocks + `-t target_seconds` trim. No-op when ref already ≥ target.
- [X] T010 `_pick_device()` — `MUSETALK_DEVICE` env override → torch.cuda.is_available → torch.backends.mps.is_available → cpu fallback. Gracefully handles torch-not-installed (returns cpu).
- [X] T011 MuseTalk-engine path: vendored-import scaffold in `_musetalk_infer()` raises `NotImplementedError` until scripts/install_musetalk.sh has been validated on a real GPU host (real integration is Phase-2.1 follow-up). **F8 aspect-ratio crop**: implemented in `_crop_face_region_to_9_16()` and called from `run()` whenever `face_bbox` is provided — works for both mock + musetalk paths.
- [X] T012 Mock-engine path: `_mock_infer()` re-encodes reference to clean MP4 via FFmpeg (no inference). Default LIP_SYNC_ENGINE=mock so dev hosts without GPU/MPS work out-of-the-box.
- [X] T013 Created `MoneyPrinterTurbo/app/services/modes/ugc_avatar.py` — full registry entry. `generate_script` reuses `llm.generate_marketing_script` (R4) with voice-locale fallback (i18n); `generate_terms` returns `[]`; `select_visuals_strategy` returns `"user_uploaded"`.
- [X] T014 Registered `ugc_avatar` in `MoneyPrinterTurbo/app/services/modes/__init__.py`. `modes.supported()` now returns `['short', 'faceless', 'long', 'ugc_avatar']`.
- [X] T015 task.py — branched at the `# 5. Get video materials` step: when `mode=="ugc_avatar"`, skip stock fetch and run lip-sync instead (face-detect → ping-pong-extend → lip_sync.run → lipsync.mp4). Also branched in `generate_final_videos` to skip `video.combine_videos` (which would trim the full assembly to max_clip_duration) — Mode 4 just copies lipsync.mp4 → combined-N.mp4 then runs the existing subtitle burn-in step. All typed errors mapped (speaker_reference_required, speaker_reference_not_found, no_face_detected, face_detect_failed, loop_extension_failed, lip_sync_engine_failed) per [contracts/l3-payload.md](./contracts/l3-payload.md#failure-modes).
- [X] T016 Extended `MoneyPrinterTurbo/app/controllers/v1/uploads.py` with `POST /api/v1/uploads/selfie` per [contracts/selfie-upload.md](./contracts/selfie-upload.md): MIME validation (mp4/mov/webm/mkv) → 100 MB cap → ffprobe duration (5-60s band per FR-001) → fps ≥ 24 → short-side ≥ 480px → MediaPipe face-detect → reject early on any failure → `_evict_oldest_avatar_if_full()` mtime-based slot eviction → write to `storage/uploads/<tenant>/avatars/slot{N}/<uuid>.mp4` + sidecar meta.json. All 9 typed error codes from the contract mapped.
- [X] T017 Already wired — `app/router.py:19` does `include_router(uploads.router)`. T016's new endpoints (`POST /api/v1/uploads/selfie` + `GET /api/v1/uploads/selfie/recent`) registered automatically because they live in the same `uploads.py` module. Verified via `python -c "from app.controllers.v1 import uploads; for r in uploads.router.routes: print(r.methods, r.path)"` — both routes present.
- [X] T018 Added `tenant_avatar_dir(tenant_id, slot=None, create=True)` to `MoneyPrinterTurbo/app/utils/utils.py`. Sanitises tenant_id; rejects slot ∉ {1,2,3}; returns `storage/uploads/<tenant>/avatars/[slotN]/`. Used by both T016 (upload write) and T032 (list-recent scan).
- [X] T019 [P] L1 scaffold at `visualai-frontend/src/app/modes/ugc-avatar/page.tsx` — Sidebar + 4-step progress band + step-1 placeholder card. Phase 3's tasks (T021–T029) replace the placeholders with real upload + script + voice + generate UI.
- [X] T020 [P] L2 — extended existing `visualai-orchestration/app/routes/uploads.py` (already wired in main.py) with `POST /api/v1/avatars/upload` (multipart proxy → L3 `/api/v1/uploads/selfie`) and `GET /api/v1/avatars/recent` (proxy → L3 `/api/v1/uploads/selfie/recent`). Reuses the existing `_proxy_upload` helper.

**Checkpoint**: L3 schema accepts `mode=ugc_avatar`; `lip_sync.py` callable; selfie upload endpoint live (even if L1 isn't using it yet); placeholder L1 + L2 routes exist. **User-story implementation can now begin.**

---

## Phase 3: User Story 1 — Auto-mode UGC ad from selfie + brief (Priority: P1) 🎯 MVP

**Goal**: Creator uploads a 5-15s selfie, types a product brief, picks a voice, clicks Generate, and within ~3 minutes gets back a 9:16 vertical MP4 of their face mouthing a freshly-written hook→body→CTA marketing script.

**Independent Test**: From the wizard, upload one selfie + one product subject → wait for completion → open the resulting MP4. Verify the face matches the selfie, mouth syncs to the audio, audio is in the chosen voice's locale, script is on-topic, and the output is 9:16 vertical.

### Implementation for User Story 1

- [ ] T021 [P] [US1] Implement L1 `<SelfieRecorder>` component in `visualai-frontend/src/components/selfie-recorder.tsx`: native `MediaRecorder` API for in-browser capture; props for `onRecorded(file: Blob)`. Fallback drag-and-drop for upload.
- [ ] T022 [P] [US1] Create L1 helper `visualai-frontend/src/lib/selfie-upload.ts`: `uploadSelfie(file)` POSTs to `/api/avatars/upload`; `listRecentSelfies()` GETs the last-3 (returns `[{slot, uuid, path, face_bbox, ...}]`); types mirror data-model.md Entity 1.
- [ ] T023 [P] [US1] Create L1 helper `visualai-frontend/src/lib/ugc-avatar.ts`: wizard state machine + `submitGenerate(state)` that POSTs to `/api/generate` with `mode="ugc_avatar"`, `speaker_reference_path`, voice, subject, etc. Also export `cancelGenerate(taskId)` that POSTs to `/api/generate/{taskId}/cancel` (used by T037).
- [ ] T024 [P] [US1] Create L1 API proxy `visualai-frontend/src/app/api/avatars/upload/route.ts`: POST handler that forwards multipart body to L2 `POST /api/v1/avatars/upload` via the existing `layer2Fetch` helper. Returns L2's response unchanged.
- [ ] T025 [US1] Wire L1 wizard step 1 (Selfie) in `visualai-frontend/src/app/modes/ugc-avatar/page.tsx`: drag-and-drop OR record OR pick-from-recent (last-3 from `listRecentSelfies()`); on selection/upload show face_bbox overlay + the chosen face thumbnail; multi-face warning banner when applicable. Block dispatch until a selfie is present (FR-001 acceptance scenario 1).
- [ ] T026 [US1] Wire L1 wizard step 2 (Script) in same page: subject textarea (Auto mode is default for US1); pre-fills helpful examples; counts characters.
- [ ] T027 [US1] Wire L1 wizard step 3 (Voice) in same page: import `VOICE_GROUPS` from `visualai-frontend/src/lib/voices.ts` and render the same multilingual `<optgroup>`s used in Mode 2's wizard. Default voice = `DEFAULT_VOICE_ID`.
- [ ] T028 [US1] Wire L1 wizard step 4 (Generate) in same page: call `submitGenerate()` from T023 → poll `/api/status/{taskId}` every 4s → render progress stage labels (Validating selfie → Script → Voice → Loop → Lip-sync → Subtitles → Finalizing per [contracts/l2-route.md](./contracts/l2-route.md#polling--wizard-side)) → on complete, embed the output MP4 in a `<video>` with download link.
- [ ] T029 [US1] Activate the UGC Avatar card on the dashboard at `visualai-frontend/src/app/page.tsx`: change its badge from "Coming in Step 4" to active and link it to `/modes/ugc-avatar`.
- [ ] T030 [P] [US1] Implement L2 upload proxy at `visualai-orchestration/app/routes/uploads.py` `POST /api/v1/avatars/upload`: forward multipart body unchanged to L3 `POST /api/v1/uploads/selfie` via `app/forwarder.py`'s helper. Inject `X-Tenant-Id` + `X-User-Id` headers from the demo bearer.
- [ ] T031 [P] [US1] Implement L1 list-recent proxy at `visualai-frontend/src/app/api/avatars/recent/route.ts`: GET handler that proxies to L2 `GET /api/v1/avatars/recent`. Used by `listRecentSelfies()` from T022. **(Was previously a "decide later" item; firm task per analyze finding F6.)**
- [X] T032 [P] [US1] Implemented L3 list-recent endpoint `GET /api/v1/uploads/selfie/recent` in the same `uploads.py` — scans `storage/uploads/<tenant>/avatars/slot{1,2,3}/` for `.meta.json` sidecars, sorts by mp4 mtime descending, returns `{items: [...]}` with up to 3 entries. Empty array when no slots occupied. Pulled forward from Phase 3 because it shares the file with T016.
- [ ] T033 [P] [US1] Implement L2 list-recent proxy at `visualai-orchestration/app/routes/uploads.py` `GET /api/v1/avatars/recent`: forward to L3's `GET /api/v1/uploads/selfie/recent` via the existing `forward_request` helper. Inject `X-Tenant-Id` from bearer.
- [ ] T034 [US1] Extend `_should_orchestrate()` in `visualai-orchestration/app/routes/videos.py` to also return `"ugc_avatar"` when `mode == "ugc_avatar"` AND `script_mode in (None, "", "auto")` AND `speaker_reference_path` present. Reject without orchestration when `speaker_reference_path` is missing (return 400).
- [ ] T035 [US1] Add `_orchestrate_ugc_avatar()` helper in `visualai-orchestration/app/routes/videos.py`: parallel to `_orchestrate_short` but skips the visual_relevance step (Mode 4 has no segments). Calls `marketing_script.generate_marketing_script` (reused per [research.md R4](./research.md#r4--script-generator-reuse-mode-2s-helper-or-write-a-mode-4-specific-one)), augments body with `video_script=full_text`, `script_mode="verbatim"`, leaves `speaker_reference_path` intact, drops `pre_signed_clip_urls` and `segments` fields explicitly to None.
- [ ] T036 [US1] Wire `_orchestrate_ugc_avatar()` into the dispatch tree in `visualai-orchestration/app/routes/videos.py` `create_video()` handler — alongside the existing `short` and `faceless` branches.

#### Cancel option (FR-010 — analyze finding F2)

- [ ] T037 [US1] L1 cancel UI: add a "Cancel" button to `visualai-frontend/src/app/modes/ugc-avatar/page.tsx` step 4 that's visible during the polling/rendering states. On click, call `cancelGenerate(taskId)` from T023, stop the poll loop, transition the wizard back to step 3 with a "Render cancelled" toast. Mirror the `<Cancel>` icon style from `lucide-react`.
- [ ] T038 [US1] L2 cancel proxy: add `POST /api/v1/videos/{task_id}/cancel` handler in `visualai-orchestration/app/routes/videos.py` that forwards to L3 `POST /api/v1/videos/{task_id}/cancel` via the existing forwarder. Returns L3's response unchanged.
- [ ] T039 [US1] L3 cancel endpoint: add `POST /api/v1/videos/{task_id}/cancel` handler in `MoneyPrinterTurbo/app/controllers/v1/video.py`. Look up the task in the existing in-memory state store (`sm.state`); flip its state to a new `TASK_STATE_CANCELLED` constant in `app/services/state.py`; the running task loop (in `task.py`) MUST cooperatively check this flag at each pipeline stage boundary (selfie_resolved, audio_synthesized, lip_synced, subtitled) and exit early with the cancellation state. Emit a loguru line including tenant + task id.

#### Smoke tests for User Story 1

- [ ] T040 [US1] Smoke test: write `MoneyPrinterTurbo/test/services/modes/test_ugc_avatar.py::test_auto_mode_english_render`. Use `LIP_SYNC_ENGINE=mock` so the test runs without GPU. Mock VideoParams with `mode="ugc_avatar"`, English voice, a fake selfie path; assert pipeline executes face-detect → audio synth → lip_sync.run → final-1.mp4 written.
- [ ] T041 [US1] Smoke test (multilingual): same file, `test_auto_mode_arabic_render`. Use `voice_name="ar-EG-SalmaNeural-Female"`; assert generated script.json has `script_mode="verbatim"` (set by L2 orchestrator), `voice_name` is Arabic, narration text contains Arabic Unicode codepoints (basic regex over U+0600–U+06FF). Verifies SC-003 + SC-004.
- [ ] T042 [US1] Cancel test: same file, `test_cancel_during_render`. Start a render (mock engine), call cancel after the audio_synthesized stage, assert the task transitions to TASK_STATE_CANCELLED within 2 stage boundaries (≤ 5s in mock mode), no `final-1.mp4` is written, and a loguru cancellation line was emitted.

**Checkpoint**: User Story 1 fully functional. Wizard end-to-end works, cancel works. **Stop here for the MVP and demo.**

---

## Phase 4: User Story 2 — Verbatim mode (Priority: P2)

**Goal**: Creator pastes their own script, system uses it word-for-word with no LLM intervention. Useful for regulated copy (legal, medical, financial).

**Independent Test**: Upload selfie + paste a known script + flip script_mode to Verbatim + Generate. Verify (a) the audio is exactly the pasted script, (b) the LLM was NOT invoked (count requests in L2 logs).

### Implementation for User Story 2

- [ ] T043 [US2] Add script_mode toggle (Auto / Verbatim / Polish pills) to `visualai-frontend/src/app/modes/ugc-avatar/page.tsx` step 2 (Script). Mirror the toggle pattern already used in `src/app/modes/short-video/page.tsx`.
- [ ] T044 [US2] Show a script editor `<textarea>` in step 2 of `visualai-frontend/src/app/modes/ugc-avatar/page.tsx` when Verbatim is selected; hide it when Auto. Bind via `WizardScriptState` from `src/lib/script-mode.ts` (existing).
- [ ] T045 [US2] Block the Generate button in `visualai-frontend/src/app/modes/ugc-avatar/page.tsx` when Verbatim is selected AND the script field is empty. Surface "Verbatim mode requires a non-empty script" inline (FR-013 acceptance scenario 2).
- [ ] T046 [US2] Verify `_should_orchestrate()` in `visualai-orchestration/app/routes/videos.py` returns None for `mode="ugc_avatar"` when `script_mode="verbatim"` (passthrough path). The L1 body should still include `speaker_reference_path` so L3's controller routes it correctly.
- [ ] T047 [US2] Smoke test in `MoneyPrinterTurbo/test/services/modes/test_ugc_avatar.py::test_verbatim_mode`: mock VideoParams with `mode="ugc_avatar"`, `script_mode="verbatim"`, a fixed `video_script="Trust us, we're licensed in 47 states."`. Assert `task.py`'s `generate_video_script()` returns the script unchanged (no LLM call) and the rendered audio length matches (within ±0.2s).

**Checkpoint**: User Stories 1 + 2 both work independently.

---

## Phase 5: User Story 3 — Polish mode (Priority: P3)

**Goal**: Creator gives rough notes, LLM polishes them into a tight Hook→Body→CTA while preserving facts. Bridges Auto (full creativity) and Verbatim (zero intervention).

**Independent Test**: Upload selfie + paste rough bullet points + flip to Polish + Generate. Verify the output narration covers all the original points but in polished prose.

### Implementation for User Story 3

- [ ] T048 [US3] Add the Polish pill to the script_mode toggle from T043 in `visualai-frontend/src/app/modes/ugc-avatar/page.tsx`. When Polish is selected, the textarea label changes from "Your script" to "Rough notes / brief".
- [ ] T049 [US3] Pass `script_mode="polish"` and `script_brief=<textarea contents>` through the L1 → L2 → L3 path in the same shape Mode 2 uses (existing `scriptStateToParams()` from `src/lib/script-mode.ts`).
- [ ] T050 [US3] Verify `_should_orchestrate()` in `visualai-orchestration/app/routes/videos.py` returns None for `script_mode="polish"` (passthrough path; L3's existing polish_script handles it via `task.py` polish branch with the voice-locale language fallback already shipped in spec i18n).
- [ ] T051 [US3] Smoke test in `MoneyPrinterTurbo/test/services/modes/test_ugc_avatar.py::test_polish_mode`: mock VideoParams with `mode="ugc_avatar"`, `script_mode="polish"`, brief like `"morning coffee, single origin, $12 per bag, 30-day money back"`. Assert `polish_script` was invoked, the four facts appear (substring) in the output, and language matches voice locale.

**Checkpoint**: All three user stories work end-to-end. Mode 4 feature-complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge-case tests, error mapping, performance benchmark, docs, and the constitutional compliance audit before merge.

- [ ] T052 [P] Loop seam smoothing test in `MoneyPrinterTurbo/test/services/test_lip_sync.py::test_extend_reference_smoothness`: run `extend_reference_to_duration` on a fixture clip, decode the output, sample frames at the loop seams (every `ref_duration` mark), and assert SSIM between frame N and frame N+1 ≥ 0.85 (no jump cut).
- [ ] T053 [P] Last-3 eviction test in `MoneyPrinterTurbo/test/controllers/v1/test_uploads.py::test_eviction_keeps_three`: upload 5 selfies in sequence; assert exactly 3 files remain on disk; assert the oldest 2 were deleted; assert filesystem state is consistent (no `<uuid>.meta.json` orphans).
- [ ] T054 [P] Face-validation rejection test in `MoneyPrinterTurbo/test/controllers/v1/test_uploads.py::test_no_face_rejection`: upload a landscape MP4 fixture (no face); assert HTTP 400 + `error_code="no_face_detected"` + no file written.
- [ ] T055 [P] Audio-overflow ping-pong end-to-end test in `MoneyPrinterTurbo/test/services/modes/test_ugc_avatar.py::test_audio_overflow_loops_visuals`: 5-second selfie + 30-second target script + `LIP_SYNC_ENGINE=mock` (so we test the loop step but skip MuseTalk inference). Assert L3 logs include `extend_reference_to_duration: ref=5.0s target≈30.0s` and the final video duration is ≈30s ±0.2s.
- [ ] T056 [P] Typed-error map test in `MoneyPrinterTurbo/test/controllers/v1/test_uploads.py::test_error_codes`: drive each error path (oversize file, bad format, low resolution, low fps, audio-only, no face, duration < 5s, duration > 60s) and assert each returns the corresponding `error_code` from [contracts/selfie-upload.md](./contracts/selfie-upload.md#error-code-matrix).
- [ ] T057 [P] Update `MoneyPrinterTurbo/CLAUDE.md` with a Mode 4 section under "Active Technologies" — note MuseTalk dep, mediapipe, lip_sync.py module, Mode 4 mode-registry entry. Mirror the format used by spec 016 (Mode 3) entry already there.
- [ ] T058 [P] Update `visualai-orchestration/CLAUDE.md` with the new Mode 4 orchestrator branch description (passthrough for ugc_avatar; mirrors short orchestrator without visual_relevance).
- [ ] T059 [P] Update `visualai-frontend/CLAUDE.md` with the new `modes/ugc-avatar/` wizard route + selfie-upload helper.
- [ ] T060 [P] Performance-benchmark fixture in `MoneyPrinterTurbo/test/services/modes/test_ugc_avatar_perf.py::test_render_time_target` (analyze finding F4 / SC-001): with a real MuseTalk engine (skipped via `pytest.mark.skipif(LIP_SYNC_ENGINE == "mock", ...)`), render a 30-second target output and assert wall-clock < 180s; render a 5-minute target output and assert < 8 minutes. Test class skipped on hosts without GPU/MPS. Document expected hardware in the test docstring.
- [ ] T061 Run [quickstart.md](./quickstart.md) smoke tests 1-6 sequentially against running localhost L1+L2+L3; document results inline in the file (commit-friendly: a one-line "Last verified 2026-MM-DD" stamp at the bottom).
- [ ] T062 My Assets surface verification (analyze finding F7): after T061's smoke renders complete, manually verify the new Mode 4 outputs appear in the existing My Assets list (`/my-assets` or equivalent in L1) under each tenant. No code changes expected — Mode 4 outputs land in the same `storage/tasks/` shape as Mode 2/3/5 — but a one-time confirmation prevents silent regressions. Document in the same quickstart.md "Last verified" footer.
- [ ] T063 Constitutional compliance audit: in the PR body for the Mode 4 implementation commit, explicitly cite (a) Constitution v1.2.0 amendment landed, (b) `app/services/lip_sync.py` justification per [plan.md § Complexity Tracking](./plan.md#complexity-tracking), (c) the affected fork-surfaces (`schema.py`, `task.py`, `modes/ugc_avatar.py`, `controllers/v1/uploads.py`, `controllers/v1/video.py` for the cancel endpoint). Required by Constitution §Development Workflow.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 finishing (especially T001 constitution amendment + T002–T003 dependencies installed). **Blocks all user stories.**
- **Phase 3 (US1, P1)**: Depends on Phase 2. Once Phase 2 is done, US1 is fully unblocked. Internally: L1 tasks (T021–T029, T031, T037), L2 tasks (T030, T033–T036, T038), and L3 tasks (T032, T039–T042) run mostly in parallel by repo with sequencing within each.
- **Phase 4 (US2, P2)**: Depends on Phase 2 + the L1 wizard scaffold from Phase 3 (T025+). Stand-alone otherwise.
- **Phase 5 (US3, P3)**: Depends on Phase 2 + the L1 script-mode toggle from Phase 4 (T043). Stand-alone otherwise.
- **Phase 6 (Polish)**: Most tasks depend only on the implementation existing. Run after Phase 3 lands at minimum (Phase 4–5 for the script-mode-specific tests).

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2 done.
- **US2 (P2)**: Builds on US1's wizard scaffold (T025) — the script_mode toggle is added INTO US1's page. Otherwise independent.
- **US3 (P3)**: Builds on US2's script_mode toggle infrastructure (T043, T044). Otherwise independent.

### Cancel-option dependencies (T037–T039, T042)

- T039 (L3 cancel endpoint) depends on T015 (task.py extension) — needs task-state hooks at pipeline stage boundaries.
- T038 (L2 cancel proxy) depends on T039 only as the upstream URL — can be coded in parallel.
- T037 (L1 cancel UI) depends on T028 (polling step) being implemented so the cancel button has the right state to attach to.
- T042 (cancel test) depends on all three.

### List-recent-selfies dependencies (T031–T033)

- T032 (L3 list endpoint) is independent.
- T033 (L2 proxy) depends on T032.
- T031 (L1 fetch) depends on T033.
- T025 (L1 wizard step 1) consumes the list-recent results — so T025 should run after T031 conceptually (or stub the list call in T025 and wire later).

### Parallel Opportunities

- All Phase 1 tasks T002–T005 marked [P] run in parallel (different files).
- Phase 2's `lip_sync.py` internals — T008 (face detect), T009 (loop), T010 (device pick) — run in parallel after T007 creates the module skeleton.
- Phase 3's L1 helpers (T021–T024, T031), L2 endpoints (T030, T033, T038), and L3 endpoints (T032, T039) run in parallel within their respective layers.
- Phase 6's tests T052–T056, T060 are independent test files — full parallel.
- Phase 6's CLAUDE.md updates T057–T059 are different repos — full parallel.

---

## Parallel Example: Phase 3 (User Story 1)

After Phase 2 completes, kick off this parallel batch:

```text
# Three repos in parallel — different teams or different sessions.

# L1 stream
Task: "T021 [P] [US1] Implement <SelfieRecorder> component"
Task: "T022 [P] [US1] Create selfie-upload.ts"
Task: "T023 [P] [US1] Create ugc-avatar.ts (incl. cancelGenerate)"
Task: "T024 [P] [US1] Create upload API proxy"
Task: "T031 [P] [US1] Create list-recent API proxy"

# L2 stream
Task: "T030 [P] [US1] Implement L2 upload proxy"
Task: "T033 [P] [US1] Implement L2 list-recent proxy"

# L3 stream
Task: "T032 [P] [US1] Implement L3 list-recent endpoint"

# Then sequential within each story
T025 → T026 → T027 → T028 → T029  (L1 wizard wiring)
T034 → T035 → T036                  (L2 orchestrator wiring)
T037 → T038 → T039 → T042           (cancel feature, end-to-end)
T040 → T041                         (smoke tests)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Land Phase 1 (Setup) — single-PR `chore:` constitutional amendment + deps.
2. Land Phase 2 (Foundational) — single-PR or two-PR sequence. Smoke that L3 accepts `mode="ugc_avatar"` payloads with mock engine.
3. Land Phase 3 (US1) — feature PR. Demo Mode 4 end-to-end with one selfie + English voice + Arabic voice (verifies SC-003 + SC-004) + cancel button works.
4. **STOP here for MVP demo.** US2 + US3 are nice-to-haves; ship US1 first to prove the lip-sync pipeline.

### Incremental Delivery

| Step | Lands | Customer-visible value |
|---|---|---|
| 1 | Phase 1 + Phase 2 | None — internal foundation |
| 2 | Phase 3 (US1) | Auto-mode UGC ad creation + cancel. **MVP shippable here.** |
| 3 | Phase 4 (US2) | Verbatim script for regulated/exact copy |
| 4 | Phase 5 (US3) | Polish mode for creators with notes |
| 5 | Phase 6 | Tests + perf benchmark + docs + cross-repo CLAUDE.md updates + constitutional audit |

### Parallel Team Strategy

With multiple developers/sessions:

1. Phase 1 + Phase 2 done together (foundation must complete before any UI work).
2. Once Phase 2 is done:
   - Dev A: L1 wizard tasks (T021–T029, T031, T037, then T043–T045, T048–T049)
   - Dev B: L2 orchestrator tasks (T030, T033–T036, T038, T046, T050)
   - Dev C: L3 endpoints + cancel + smoke tests (T032, T039–T042, T047, T051, T052–T056, T060)
3. Phase 6 docs (T057–T059) + audit (T063) go last; require all implementation work to settle.

---

## Notes

- [P] tasks = different files, no in-flight dependencies.
- [Story] label maps task to specific user story for traceability.
- Each user story should be independently completable and testable — the MVP STOP point is end of Phase 3.
- Constitution amendment (T001) MUST land before T013–T016 (Mode 4 mode registry + dispatch). Otherwise Constitution Principle V is silently violated.
- Avoid: vague tasks, same-file conflicts within a parallel batch, cross-story dependencies that break independence.

## Format Validation

All 63 tasks above conform to the required format:
- Every task starts with `- [ ]` checkbox ✓
- Every task has a sequential ID `T001`–`T063` ✓
- `[P]` marker present where parallelizable ✓
- `[US1]` / `[US2]` / `[US3]` labels present in story phases (T021–T051) ✓
- Setup / Foundational / Polish phase tasks have NO story label (T001–T020, T052–T063) ✓
- Every task has a concrete file path ✓

## Cross-reference: analyze findings → resolution

| Finding | Severity | Resolution in this revision |
|---|---|---|
| F1 — FR-001 5-15s vs ≤60s wording | MEDIUM | spec.md FR-001 rewritten (5-60s upload, first 15s used as reference); T016 + T056 reflect the wider duration band. |
| F2 — Cancel option not in tasks | MEDIUM | New tasks T037 (L1 cancel UI), T038 (L2 cancel proxy), T039 (L3 cancel endpoint), T042 (cancel test). |
| F3 — Credit-refund FR-011 | LOW | spec.md FR-011 annotated — refund deferred until spec 008 (NEX-461) lands. |
| F4 — SC-001 perf benchmark missing | LOW | New task T060 — performance-benchmark fixture. |
| F5 — "frame-accurate" wording | LOW | spec.md FR-006 rewritten to reference FR-007's ±0.2s tolerance. |
| F6 — T031 deferred decision | LOW | Decision committed: list-recent endpoint chain firm at T031 (L1) + T032 (L3) + T033 (L2). |
| F7 — My Assets verification | LOW | New task T062 — manual verification step after smoke run. |
| F8 — Aspect-ratio cropping | LOW | T011 extended with explicit 9:16 face-centered crop logic for any source aspect ratio. |
