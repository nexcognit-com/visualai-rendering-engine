---
description: "Task list for feature 010 — Music Track Control + Custom Uploads"
---

# Tasks: Music Track Control + Custom Uploads

**Input**: Design documents from `/specs/010-music-control/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Smoke tests are MANDATORY per the constitution's §Development Workflow rule ("new mode code requires at least one smoke test exercising the rendering path with mocked Layer 2 inputs"). The contracts in `contracts/` define 16 acceptance tests (AU-1..AU-8 + MC-1..MC-8); these are scheduled as task items below.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. The four user stories from spec.md are:

- **US1** (P1): Creator picks a music track (Preset/Random + None modes) — the minimum viable wizard music UX
- **US2** (P2): Creator uploads a custom audio file — adds the upload endpoint + Upload mode in the wizard
- **US3** (P2): Creator adjusts music volume — the slider + 80%-warning UX
- **US4** (P3): Brand Library forward-compat (schema-only) — single test asserting the `bgm_file` field accepts future paths

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4)
- All file paths are relative to the project root `/Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo/` (or `visualai-frontend/` sibling repo where noted)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: minimal preparation — most setup either already happened in spec 009 or is trivial.

- [x] T001 Confirm `storage/uploads/` is gitignored (idempotent; spec 009's T001 may have already done this). Path: `.gitignore`. **Done — `/storage/` covers it.**
- [x] T002 [P] Add `_make_synthetic_audio(path: str, duration_s: float = 1.0, format: str = "wav")` helper to the shared test fixtures so audio smoke tests can produce sine-wave WAV/MP3/OGG/M4A files via NumPy + ffmpeg without committed binary fixtures (see [research.md R7](./research.md)). Path: `test/services/test_helpers.py` (extend the file created by spec 009 task T002; if spec 009 hasn't shipped, create the file with both the video-stub and audio-stub helpers). **Done — file created with `make_synthetic_audio()`; verified producing 0.5s WAV (44KB) and MP3 (4.6KB).**

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared backend endpoints + frontend types/proxies + the conditional-emission logic in `/api/generate` that every user story depends on. Once Phase 2 is complete, US1 / US2 / US3 / US4 can each be developed in parallel.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Backend (Layer 3)

- [ ] T003 Extend the audio upload endpoint at `POST /api/v1/uploads/audio` per [contracts/audio-upload-endpoint.md](./contracts/audio-upload-endpoint.md). Reuse spec 009's `_validate_upload(file, allowed_mimes, max_bytes)` helper (or create it if 010 ships first). Validate MIME (MP3/WAV/OGG/M4A), size (≤ 10 MB); save to `storage/uploads/<uuid>.<ext>`; probe duration via `ffprobe` (with `AudioFileClip.duration` fallback per [research.md R1](./research.md)); return `{path, size_bytes, mime_type, duration_seconds}`. On probe failure, delete the persisted file before returning 415. Path: `app/controllers/v1/uploads.py`.
- [ ] T004 [P] Create the bundled-track enumeration endpoint `GET /api/v1/bgm/tracks` per [contracts/music-config-contract.md](./contracts/music-config-contract.md). List `.mp3`/`.wav`/`.ogg`/`.m4a` files in `resource/songs/`, ffprobe each for duration, sort alphabetically by filename, return `{tracks: [{name, path, duration_seconds}], count}`. Path: `app/controllers/v1/bgm.py`.
- [ ] T005 Register the new bgm router in the application root router. Path: `app/router.py` (add `root_api_router.include_router(bgm.router)` alongside the existing routers around line 16). Depends on T004.

### Frontend (Layer 1)

- [ ] T006 [P] Create the TypeScript `MusicConfig` type matching the wire shape from [contracts/music-config-contract.md](./contracts/music-config-contract.md) — three-mode discriminated union (`{mode: "preset", track_path: string} | {mode: "upload", track_path: string, duration_seconds: number} | {mode: "none"}`) plus a `volume_pct: number` (0–100). Path: `visualai-frontend/src/lib/music.ts`.
- [ ] T007 [P] Create the audio upload proxy at `POST /api/upload-audio` that accepts `multipart/form-data` from the browser, re-multiparts to MPT's `/api/v1/uploads/audio`, and forwards the JSON response (or error). Path: `visualai-frontend/src/app/api/upload-audio/route.ts`.
- [ ] T008 [P] Create the bundled-tracks proxy at `GET /api/bgm-tracks` that fetches from MPT's `/api/v1/bgm/tracks` and returns the JSON to the browser. Path: `visualai-frontend/src/app/api/bgm-tracks/route.ts`.
- [ ] T009 Extend `/api/generate` to **conditionally** include `bgm_type`, `bgm_file`, `bgm_volume` in the request body to MPT — ONLY when the wizard has actively configured the music panel (per [research.md R4](./research.md), the conditional-emission rule that guarantees zero regression for legacy/unmodified callers). Path: `visualai-frontend/src/app/api/generate/route.ts`. Depends on T006 for the type.

**Checkpoint**: Foundation ready. Backend endpoints respond, frontend types + proxies exist, the conditional-emission rule is wired. All four user stories can now begin in parallel.

---

## Phase 3: User Story 1 — Creator picks a music track (Priority: P1) 🎯 MVP

**Goal**: A creator opens Mode 2's wizard, picks a music track from the bundled library OR "Random" OR "None", submits, and the rendered MP4 reflects the choice.

**Independent Test**: Generate a render with the wizard's music selector at "None"; verify voiceover-only audio. Generate a second render with a specific bundled track selected; verify that exact track audibly plays underneath the voiceover. The two renders MUST clearly differ in audio content.

### Tests for User Story 1 (mandatory smoke + contract tests)

- [ ] T010 [P] [US1] Smoke test MC-1 (zero-regression default path): POST `/api/v1/videos` with no `bgm_*` fields; assert Pydantic accepts and the rendered MP4 has voiceover + a random bundled BGM at default 0.2 volume — i.e., today's behavior. Path: `test/services/test_music_config.py`.
- [ ] T011 [P] [US1] Smoke test MC-2 (random preset path): POST with `bgm_type="random"`, `bgm_volume=0.2`; assert one of the bundled tracks is selected (verify `final-1.mp4` audio includes BGM frequency content). Path: `test/services/test_music_config.py`.
- [ ] T012 [P] [US1] Smoke test MC-3 (specific bundled track): POST with `bgm_type="file"`, `bgm_file="resource/songs/output005.mp3"`, `bgm_volume=0.5`; assert `output005.mp3` is the BGM mixed in. Path: `test/services/test_music_config.py`.
- [ ] T013 [P] [US1] Smoke test MC-5 (voiceover-only path): POST with `bgm_type=""`; assert the rendered MP4's audio track contains only voiceover (no BGM mix). Verify by ffprobe analysis: BGM frequency band (100–500 Hz when voiceover quiet) has near-zero energy. Path: `test/services/test_music_config.py`.
- [ ] T014 [P] [US1] Smoke test MC-8 (`/api/v1/bgm/tracks` enumeration): GET the endpoint; assert response shape matches the contract; assert `count == len(os.listdir("resource/songs/"))` and tracks are sorted alphabetically. Path: `test/controllers/test_bgm_tracks.py`.

### Implementation for User Story 1

- [ ] T015 [US1] Add a "Music" panel to wizard Step 3 alongside the existing voice + music placeholder (per the 5-step plan's promised Step 3 layout). The panel has a mode selector (radio buttons or pill tabs) for Preset / Upload (placeholder, wired in US2) / None. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`.
- [ ] T016 [US1] Implement Preset mode: on Step 3 mount, fetch `/api/bgm-tracks` once, populate the dropdown with `{name, duration_seconds}` rows, default to "Random" at the top of the list. When the creator picks "Random", set wizard state `{mode: "preset", track_path: ""}` (empty signals random). When the creator picks a specific track, set `{mode: "preset", track_path: "resource/songs/output<NNN>.mp3"}`. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T015.
- [ ] T017 [US1] Implement None mode: when picked, set wizard state `{mode: "none"}`. Show "voiceover only — no music will play" hint. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T015.
- [ ] T018 [US1] Translate wizard music state to `bgm_type` / `bgm_file` / `bgm_volume` payload shape in the wizard's submit handler (per the conditional-emission rule from T009). The mapping: `mode="preset"` + `track_path=""` → `bgm_type="random"`; `mode="preset"` + non-empty path → `bgm_type="file"` + `bgm_file=path`; `mode="none"` → `bgm_type=""`. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T015 + T009.
- [ ] T019 [US1] Run [quickstart.md Parts 2 + 3](./quickstart.md) (manual end-to-end verification of None mode + Preset bundled-track mode). Path: manual verification, no file change.

**Checkpoint**: User Story 1 fully functional. Creators can pick Preset/Random/None music; legacy callers unchanged. MVP delivered.

---

## Phase 4: User Story 2 — Creator uploads a custom music track (Priority: P2)

**Goal**: A creator uploads their own audio file (MP3/WAV/OGG/M4A up to 10 MB) via the wizard's Upload mode, and the rendered MP4 plays that track underneath the voiceover.

**Independent Test**: Upload a known MP3, generate a render, verify that uploaded track is audibly the BGM in the final MP4 (recognizable on spot-listen). Verify upload error paths surface inline before render starts.

### Tests for User Story 2

- [ ] T020 [P] [US2] Contract test AU-1 + AU-2 + AU-3 + AU-4 (valid uploads of all 4 formats): POST a synthetic 1 s sine-wave file in WAV, MP3, OGG, M4A; assert HTTP 201, response includes `path` matching `^storage/uploads/[0-9a-f-]{36}\.(wav|mp3|ogg|m4a)$` and `duration_seconds ≈ 1.0`. Path: `test/controllers/test_uploads_audio.py`.
- [ ] T021 [P] [US2] Contract test AU-5 + AU-6 (rejected sizes/formats): a 12 MB body returns 413 `file_too_large`; a `.flac` upload returns 400 `unsupported_format`. Path: `test/controllers/test_uploads_audio.py`.
- [ ] T022 [P] [US2] Contract test AU-7 (corrupt audio): POST plain text bytes claiming `audio/mpeg` MIME; assert HTTP 415 `invalid_audio` AND the persisted file has been deleted from `storage/uploads/` (no orphan UUID). Path: `test/controllers/test_uploads_audio.py`.
- [ ] T023 [P] [US2] Contract test AU-8 (filename safety): upload with filename `../../etc/passwd.mp3`; assert response `path` starts with `storage/uploads/` + UUID4 + `.mp3` (NOT path-traversal-preserved). Path: `test/controllers/test_uploads_audio.py`.
- [ ] T024 [P] [US2] Smoke test MC-4 (custom upload renders): upload a 1 s sine-wave MP3 via the audio upload endpoint, then POST `/api/v1/videos` with `bgm_type="file"`, `bgm_file=<returned path>`, `bgm_volume=0.3`; assert the rendered MP4's audio includes the uploaded sine-wave's frequency content. Path: `test/services/test_music_config.py`.

### Implementation for User Story 2

- [ ] T025 [US2] Implement Upload mode in the Music panel: hidden `<input type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4">` triggered by a styled button. On file change, validate client-side (size ≤ 10 MB, MIME in allowed list), POST `FormData` to `/api/upload-audio`, store the returned `path` + `duration_seconds` in wizard state as `{mode: "upload", track_path: <path>, duration_seconds: <duration>}`. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T015.
- [ ] T026 [US2] Display the uploaded track's duration + filename in the Music panel after a successful upload. Format the duration as `M:SS` (e.g., `2:18`). Display a hint: "your track is N seconds — it will loop / be truncated to fit your video" with the right verb based on whether duration > or < expected video duration (~30 s for Mode 2). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T025.
- [ ] T027 [US2] Surface upload errors inline near the file input (FR-011): typed messages for `unsupported_format`, `file_too_large`, `invalid_audio`, `storage_write_failed`. The render does NOT start while errors are unresolved. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T025.
- [ ] T028 [US2] Run [quickstart.md Part 4](./quickstart.md) (manual custom-upload end-to-end verification): upload an MP3, render, listen back. Path: manual verification.

**Checkpoint**: User Story 2 complete. Creators can upload custom audio; both US1 (preset) and US2 (upload) work independently.

---

## Phase 5: User Story 3 — Creator adjusts music volume (Priority: P2)

**Goal**: A volume slider in the Music panel maps creator-friendly 0–100 % to the backend's 0.0–1.0 `bgm_volume` field, with a soft warning at ≥ 80 % (overpowers voice) but no hard block.

**Independent Test**: Generate two renders of the same track at 20 % vs. 60 %; the second's BGM is audibly louder. The wizard surfaces a warning at slider ≥ 80 %.

### Tests for User Story 3

- [ ] T029 [P] [US3] Smoke test MC-6 (out-of-range volume — wizard clamps before submission): the wizard's submit handler MUST clamp `volume_pct` to [0, 100] before division by 100; assert that no payload with `bgm_volume > 1.0` or `< 0.0` ever leaves the wizard. Implement as a unit test of the wizard's mapping function (extracted into `visualai-frontend/src/lib/music.ts`). Path: `visualai-frontend/test/lib/music.test.ts` (or wherever the frontend's test runner lives — Vitest is typical for Next.js).

### Implementation for User Story 3

- [ ] T030 [US3] Add the volume slider to the Music panel: integer 0–100 range, default 20, displayed beside its current value (e.g., "20%"). Visible whenever `mode != "none"` (a None render produces no audible music regardless of slider). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T015.
- [ ] T031 [US3] Add the 80 %-warning copy under the slider: text appears when slider ≥ 80, content "may overpower voiceover — preview recommended" (preview itself is deferred, the warning still fires). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T030.
- [ ] T032 [US3] In the wizard's submit handler, divide `volume_pct` by 100.0 to produce `bgm_volume` as a float; clamp result to [0.0, 1.0] defensively. Path: `visualai-frontend/src/lib/music.ts` (extract the mapping function so T029 can unit-test it) + `visualai-frontend/src/app/modes/short-video/page.tsx`. Depends on T030 + T009.
- [ ] T033 [US3] Run [quickstart.md Part 5](./quickstart.md) (manual volume verification): two renders at 20 % vs. 60 %; spot-listen for clearly audible difference. Path: manual verification.

**Checkpoint**: User Story 3 complete. All three primary stories work independently.

---

## Phase 6: User Story 4 — Brand Library Forward-Compat (Priority: P3, schema-only)

**Goal**: The existing `bgm_file` field on `VideoParams` accepts future Brand Library asset paths (`brand-library/<tenant>/music/<asset>.<ext>`) without rejection. Confirms FR-009 + SC-006.

**Independent Test**: A synthetic API request with `bgm_file: "brand-library/tenant_abc/music/intro_v3.mp3"` validates against the Pydantic model with no errors.

### Tests for User Story 4

- [ ] T034 [P] [US4] Schema test MC-7: instantiate `VideoParams(video_subject="x", bgm_type="file", bgm_file="brand-library/tenant_abc/music/intro_v3.mp3", bgm_volume=0.4)`; assert it validates cleanly. Path: `test/models/test_schema_bgm.py`.

**Checkpoint**: Forward-compat hook locked in; future Brand Library writer won't require a schema migration.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: tasks that span multiple stories or finalize the feature for merge.

- [ ] T035 [P] Surface "this render had custom music" indicator on the My Assets card when `task.bgm_file` starts with `storage/uploads/`. Pull `bgm_file` from the existing `script.json` artifact in `app/api/history/route.ts` and render a small badge in the My Assets grid. Path: `visualai-frontend/src/app/api/history/route.ts` and `visualai-frontend/src/app/assets/page.tsx`.
- [ ] T036 Update `STEP1_DEBT.md` to note that this feature exposed existing `bgm_*` fields without schema changes and continues debts #2 (no tenant scoping on uploads) and #4 (mode prompts inline). Path: `STEP1_DEBT.md`.
- [ ] T037 [P] Run [quickstart.md Parts 1, 6a, 6b, 6c, 7, 8, 9](./quickstart.md): zero-regression baseline (Part 1), all error-surfacing paths (Part 6), full pytest run (Part 7), schema forward-compat (Part 8), bundled-track enumeration (Part 9). Path: manual verification.
- [ ] T038 Constitution compliance check: `git diff --stat origin/main..HEAD` MUST show ZERO changes to `app/services/video.py` AND ZERO changes to `app/models/schema.py` (Principle II rebase-clean rule + spec's no-new-fields invariant). If either file changed, abort the merge. Path: manual verification.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. **BLOCKS all user stories.**
- **User Stories (Phase 3+)**: All depend on Foundational completion.
  - US1 (P1) is the MVP — ship and validate independently.
  - US2 (P2) and US3 (P2) build on US1's wizard panel skeleton (T015) but exercise different parts of it; **both need T015 done first** but otherwise are parallel.
  - US4 (P3) is a single schema test, runnable any time after Phase 2.
- **Polish (Phase 7)**: Depends on all desired user stories being complete.

### Within Each User Story

- Tests MUST exist and FAIL before implementation (constitution: smoke tests required for new render-pipeline code).
- Backend foundational work (Phase 2) precedes any wizard UI changes.
- Music panel scaffolding (T015) precedes any mode-specific work (T016, T017, T025, T030).
- Quickstart-validation tasks (T019, T028, T033) close out each story.

### File Conflicts to Note

- `app/controllers/v1/uploads.py` — touched once (T003). **Shared with spec 009** (logo endpoint). The PR-merge order between 009 and 010 determines who creates the file vs extends it. Both PRs MUST use the shared `_validate_upload` helper.
- `app/controllers/v1/bgm.py` — new file, single task (T004).
- `app/router.py` — touched once (T005). Sequential with anything else editing it.
- `visualai-frontend/src/lib/music.ts` — touched by T006 + T032. Sequential.
- `visualai-frontend/src/app/api/generate/route.ts` — touched once (T009).
- `visualai-frontend/src/app/api/upload-audio/route.ts` — new, single task (T007).
- `visualai-frontend/src/app/api/bgm-tracks/route.ts` — new, single task (T008).
- `visualai-frontend/src/app/api/history/route.ts` — touched once (T035) — **shared with spec 009 task T035**; merge order resolves.
- `visualai-frontend/src/app/assets/page.tsx` — touched once (T035) — same shared concern as spec 009.
- `visualai-frontend/src/app/modes/short-video/page.tsx` — touched by T015, T016, T017, T018, T025, T026, T027, T030, T031, T032. **All sequential** (same file). Also shared with spec 009's wizard panel (different JSX subtree, no semantic conflict, but lexical merge order matters).
- `test/services/test_music_config.py` — touched by T010, T011, T012, T013, T024 — different test functions, all `[P]`-eligible because pytest collects them independently.
- `test/controllers/test_uploads_audio.py` — touched by T020, T021, T022, T023 — same `[P]` reasoning.
- `test/controllers/test_bgm_tracks.py` — single file, single task (T014).
- `test/models/test_schema_bgm.py` — single file, single task (T034).

### Parallel Opportunities

- **Phase 1**: T002 [P] — only one parallelizable task (T001 is trivial gitignore confirmation).
- **Phase 2 backend**: T003, T004 [P] — different files. T005 sequential (router registration depends on T004).
- **Phase 2 frontend**: T006, T007, T008 all [P] — different files. T009 depends on T006.
- **Phase 3 tests**: T010..T014 all [P] — different test functions/files; pytest collects each independently.
- **Phase 3 implementation**: T015 → (T016, T017, T018) sequential within the same file. T019 manual.
- **Phase 4 tests**: T020..T024 all [P].
- **Phase 4 implementation**: T025, T026, T027 sequential (same file).
- **Phase 5 tests**: T029 [P].
- **Phase 5 implementation**: T030, T031, T032 sequential (same file + lib).
- **Phase 6**: T034 [P], single task.
- **Phase 7**: T035, T037 [P]; T036, T038 sequential.

---

## Parallel Example: Foundational Phase 2

```bash
# Backend — T003 + T004 in parallel:
Task: "Audio upload endpoint with validation + duration probe in app/controllers/v1/uploads.py"
Task: "GET /v1/bgm/tracks endpoint listing resource/songs/ in app/controllers/v1/bgm.py"

# Frontend — T006 + T007 + T008 in parallel:
Task: "TypeScript MusicConfig type in visualai-frontend/src/lib/music.ts"
Task: "Upload-audio multipart proxy in visualai-frontend/src/app/api/upload-audio/route.ts"
Task: "Bgm-tracks proxy in visualai-frontend/src/app/api/bgm-tracks/route.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002).
2. Complete Phase 2: Foundational (T003..T009). **CRITICAL — blocks all stories.**
3. Complete Phase 3: User Story 1 (T010..T019).
4. **STOP and VALIDATE**: run [quickstart.md Parts 2 + 3](./quickstart.md). Confirm SC-002 (None) + SC-003 (Preset) pass.
5. Demo / merge as PR if ready.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready (~1 hour).
2. Add User Story 1 → Ship (MVP); ~1.5 hours total.
3. Add User Story 2 (custom upload) → Ship; ~1 hour (most of the wiring is reused from US1).
4. Add User Story 3 (volume slider) → Ship; ~30 min.
5. Add User Story 4 (schema forward-compat test) → Ship; ~5 min.
6. Polish → ~45 min total.

**Total estimated time**: 4–5 hours single-developer, single-session. Parallel-deliverable with spec 009 (different files except `uploads.py`, `history/route.ts`, `assets/page.tsx`, and the wizard `page.tsx` — all merge-resolvable).

### Constitution Compliance Reminders

- **Do not edit `app/services/video.py`** (Principle II — keep upstream MoviePy assembly code rebase-clean). T038 verifies.
- **Do not add fields to `app/models/schema.py`** — the spec's whole premise is that `bgm_type`/`bgm_file`/`bgm_volume` already exist. T038 verifies the file is also untouched.
- The PR description for this feature MUST reference Mode 2 (Short Marketing Video) and cite Master Spec §3 (Five Agent Modes) per the constitution's §Development Workflow rule for fork-surface PRs (this PR touches the fork-surface controllers directory via T003 + T005).
- The smoke tests in `test/services/test_music_config.py`, `test/controllers/test_uploads_audio.py`, `test/controllers/test_bgm_tracks.py`, and `test/models/test_schema_bgm.py` are a hard requirement — the PR MUST NOT merge without them passing locally.

---

## Notes

- `[P]` tasks = different files, no dependencies — can run in parallel.
- `[Story]` label maps task to specific user story for traceability and independent delivery.
- Each user story is independently completable and testable; halting after US1 ships a real MVP.
- The 16 contract acceptance tests are scheduled across:
  - Phase 3 (US1 owns 5: MC-1 zero-regression, MC-2 random, MC-3 specific bundled, MC-5 voiceover-only, MC-8 enumeration endpoint)
  - Phase 4 (US2 owns 5: AU-1..AU-4 valid uploads, AU-5/AU-6 rejected, AU-7 corrupt+cleanup, AU-8 filename safety, MC-4 custom-upload-renders)
  - Phase 5 (US3 owns 1: MC-6 wizard volume clamp)
  - Phase 6 (US4 owns 1: MC-7 Brand Library forward-compat)
- Commit after each task or logical group. The full feature is one PR per the SpecKit governance pattern; intra-feature commits are encouraged for review-ability.
- This feature is parallel-deliverable with spec 009; the recommended delivery order is "ship 009 + 010 in alternating commits in the same week" so the wizard's Step 3 matures together rather than landing one panel half-done.
