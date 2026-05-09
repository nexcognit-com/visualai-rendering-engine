---
description: "Task list for 019-longform-10min-fix"
---

# Tasks: Mode 3 long-form 10-minute cap + URL-expiry resilience + WebM selfie uploads

**Input**: Design documents from `/specs/019-longform-10min-fix/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/selfie-upload-mime.md, quickstart.md (all complete)

**Tests**: Test tasks ARE included because the constitution mandates `pytest test/` passing locally and at least one smoke test per new mode-touching change.

**Organization**: Tasks are grouped by user story (US1 / US2 / US3) per spec.md priority ordering. Setup and Foundational phases are minimal — this is a retroactive spec for already-shipped work, so most tasks are *verification* and *test-coverage hardening* rather than green-field implementation. Cross-layer (L1/L2) dependencies are listed in the Appendix at the bottom so the main task list stays L3-focused.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 / US2 / US3)
- File paths are exact and match the plan.md structure

## Path Conventions

Single Python project at repo root:

- App code under `app/services/`, `app/controllers/v1/`
- Tests under `test/services/`, `test/controllers/`

## Implementation status legend

- **[shipped]** — code change is already on this branch (commit `c124ebb` or `e817809`); task is to *verify* it matches spec / plan / contracts.
- **[new]** — task introduces code or test that is not yet on the branch.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm baseline; this feature does not introduce new packages or dependencies.

- [ ] T001 Verify `pyproject.toml` and `uv.lock` are unchanged on this branch — no new deps introduced. Run `git diff main..HEAD -- pyproject.toml uv.lock` and confirm empty output.
- [ ] T002 Verify FFmpeg is callable in the dev environment (`ffmpeg -version`) and supports the `lavfi` filter (`ffmpeg -filters | grep '^.. lavfi'`). Required for both the black-frame placeholder and the WebM re-encode paths.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Nothing new. Recorded so analyze does not flag a missing phase.

- [ ] T003 Confirm Constitution v1.2.0 governs this branch (`head -2 .specify/memory/constitution.md`); no amendment is required for this feature (no new mode, no new fork-surface).
- [ ] T004 Confirm `update-agent-context.sh` no-op rationale is documented in plan.md "Agent context update" section.

**Checkpoint**: Foundation verified — user story tasks can begin.

---

## Phase 3: User Story 1 — Pick a 10-minute Mode 3 target (Priority: P1) 🎯 MVP

**Goal**: Mode 3 long-form mode accepts 8-min and 10-min duration targets end-to-end and returns single-MP4 outputs at the requested length with 30–40 distinct visual segments.

**Independent Test**: Open the wizard, pick Mode 3 → 10-minute → any subject, dispatch. Within 75 minutes wall-clock, the wizard reports completion and the resulting MP4 plays at 600 ± 5 seconds with subtitles aligned across the full duration. Per quickstart.md Journey A.

### Tests for User Story 1

- [ ] T005 [shipped] [US1] Read existing `app/services/modes/long_form.py` and confirm `duration_choices_seconds == (120, 180, 240, 300, 480, 600)` and `segment_count_range == (8, 40)`. Cite the file and line numbers in the verification log.
- [ ] T006 [new] [P] [US1] Write `test/services/modes/test_long_form.py` (or extend if it already exists) with two unit tests:
  - `test_duration_choices_includes_480_and_600` — asserts both new values are present.
  - `test_segment_count_range_upper_bound_is_40` — asserts the upper bound is exactly 40.
  These are pure data-table assertions; no FFmpeg needed; runtime <1s.

### Implementation for User Story 1

- [ ] T007 [shipped] [US1] Implementation already in `app/services/modes/long_form.py`. No code change needed; the task is to confirm via `git show c124ebb -- app/services/modes/long_form.py` that the diff matches the FR-001 / FR-002 contract.

**Checkpoint**: User Story 1 fully verified — Mode 3 at the 10-min cap works end-to-end, with regression coverage in the test suite.

---

## Phase 4: User Story 2 — Long render survives expired pre-signed URLs (Priority: P2)

**Goal**: When the rendering layer's fetch step encounters HTTP 403 or 410 on a pre-signed URL, that segment is replaced by a same-duration black-frame MP4 placeholder and the render completes normally with audio + subtitle alignment intact.

**Independent Test**: Per quickstart.md Journey B — force at least one 403/410 in the fetch step and verify the render produces a final MP4 of correct duration with a black-frame at the failed segment's slot, plus a `WARNING` log line per substitution.

### Tests for User Story 2

- [ ] T008 [new] [P] [US2] Add `test/services/test_material_url_expiry.py` with these unit tests, mocking `requests.get`:
  - `test_403_short_circuits_retry_and_writes_placeholder` — single URL returns 403; confirm `out_paths` includes a placeholder file and `_write_black_frame_clip` was called once.
  - `test_410_short_circuits_retry_and_writes_placeholder` — same as above for 410.
  - `test_5xx_retries_then_succeeds` — first call 503, second call 200; confirm only one retry, no placeholder written.
  - `test_5xx_retries_then_dies_writes_placeholder` — both calls 503; confirm placeholder written.
  - `test_all_urls_dead_render_still_completes` — all five URLs return 403; confirm five placeholders written and no exception raised.
  - `test_placeholder_failure_is_terminal` — mock `_write_black_frame_clip` to raise; confirm `RuntimeError("material.fetch_failed")` is raised (FR-006).
  - `test_alignment_preserved_with_placeholders_at_indices_2_and_5` — five URLs total, indices 2 and 5 return 403 with `target_duration_seconds=4.0` and `8.0` respectively; confirm the resulting `out_paths` are still 5 entries in original order, the placeholder durations match those targets ±0.05s (via `ffprobe`), and the cumulative timeline offset of each subsequent clip equals what it would have been with all-real fetches (FR-007).
- [ ] T009 [new] [P] [US2] Add `test/services/test_black_frame_clip.py` with one integration test that actually invokes FFmpeg:
  - `test_write_black_frame_clip_produces_valid_mp4` — call `_write_black_frame_clip(tmp_path, duration_seconds=3.5)`, then `ffprobe` the result and assert codec=h264, pix_fmt=yuv420p, duration=3.5±0.05s, no audio stream, width=1280, height=720, framerate=30 (FR-004, data-model.md §BlackFramePlaceholderClip).

### Implementation for User Story 2

- [ ] T010 [shipped] [US2] Implementation already in `app/services/material.py:_download_from_pre_signed_urls` and the new `_write_black_frame_clip` helper. Verify via `git show c124ebb -- app/services/material.py` that the diff matches FR-003, FR-004, FR-005, FR-006, FR-007.
- [ ] T011 [shipped] [US2] Verify the WARNING log message format matches data-model.md §BlackFramePlaceholderClip "Logging contract": includes clip index, truncated URL (≤80 chars), and the original fetch error string.

**Checkpoint**: User Story 2 fully verified — long renders are resilient to URL expiry; coverage in unit tests + one FFmpeg-integration test, alignment explicitly asserted.

---

## Phase 5: User Story 3 — WebM selfie upload from in-browser MediaRecorder (Priority: P2)

**Goal**: A creator's in-browser-recorded selfie (WebM with VP8 or VP9 codec) uploads on the first attempt, is persisted as H.264 MP4 with no audio track, and is immediately usable as a Mode 4 speaker reference.

**Independent Test**: Per quickstart.md Journey C — record a 6–10s selfie in Chrome, click upload, confirm 200 response; on L3, `ffprobe` the persisted file and verify codec=h264, pix_fmt=yuv420p, no audio.

### Tests for User Story 3

- [ ] T012 [new] [P] [US3] Extend `test/controllers/test_image_upload.py` with `class TestSelfieUploadMimeStripping`:
  - `test_video_webm_codecs_vp8_accepted` — POST with `Content-Type: video/webm;codecs=vp8` and a valid WebM body returns 200.
  - `test_video_webm_space_after_semicolon_accepted` — `video/webm; codecs=vp9` (note the space) returns 200.
  - `test_video_webm_multi_codec_accepted` — `video/webm;codecs=vp8,opus` returns 200.
  - `test_video_x_matroska_codecs_accepted` — `video/x-matroska;codecs=h264` returns 200.
  - `test_image_png_rejected_with_original_mime_echoed` — `image/png` returns 400 with `message == "Unsupported MIME: image/png"`.
  - `test_unknown_mime_with_codec_param_rejected_with_full_original_echoed` — `video/x-flv;codecs=h263+` returns 400 with the full original string in the message (FR-010).
- [ ] T013 [new] [P] [US3] Add one parametrised integration test `test_non_mp4_persisted_as_h264_mp4_no_audio` in the same file, run for two cases:
  - `("video/webm;codecs=vp8", "/tmp/test.webm", "libvpx-vp8")` — build via `ffmpeg -f lavfi -i color=c=red:s=320x240:d=2 -c:v libvpx-vp8 /tmp/test.webm`.
  - `("video/x-matroska;codecs=h264", "/tmp/test.mkv", "libx264")` — build via `ffmpeg -f lavfi -i color=c=blue:s=320x240:d=2 -c:v libx264 /tmp/test.mkv`.
  - For each: POST the file with the matching `Content-Type`. On the persisted file (`persisted_path` in response), run `ffprobe` and assert codec=h264, pix_fmt=yuv420p, no audio stream (FR-009).

### Implementation for User Story 3

- [ ] T014 [shipped] [US3] Implementation already in `app/controllers/v1/uploads.py:upload_selfie`. Verify via `git show e817809` that the diff matches FR-008, FR-009, FR-010 and the contract in `contracts/selfie-upload-mime.md`.
- [ ] T015 [shipped] [US3] Confirm `_SELFIE_VIDEO_MIMES` allow-list contains exactly the four entries declared in the contract: `video/mp4`, `video/quicktime`, `video/webm`, `video/x-matroska`. Read `app/controllers/v1/uploads.py` and grep.

**Checkpoint**: User Story 3 fully verified — browser-recorded WebM and desktop-uploaded MKV both succeed end-to-end and persist as the canonical H.264 MP4.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Final integration, documentation, and the constitution-mandated test gate.

- [ ] T016 Run `pytest test/` from repo root. All tests in `test/services/test_material_url_expiry.py`, `test/services/test_black_frame_clip.py`, `test/services/modes/test_long_form.py`, and the extended `test/controllers/test_image_upload.py` MUST pass. No regressions in other suites.
- [ ] T017 [P] Update `STEP1_DEBT.md` if any constitution principle relaxations were inadvertently introduced by this branch. (Expected: none — this feature touches only approved fork surfaces and does not introduce credit / billing / external-API logic.)
- [ ] T018 [P] Run `git log --oneline main..HEAD` and confirm both `c124ebb` (longform + URL-expiry) and `e817809` (uploads MIME/WebM) are on the branch with Conventional Commit subjects (`feat:` and `fix:` respectively). Constitution §Development Workflow.
- [ ] T019 Smoke-test all three quickstart journeys (A, B, C) against a local L1+L2+L3 stack. Capture pass/fail per pass criterion in a brief notes file (not committed). Journey A's pass criteria explicitly include: (a) 8-min and 10-min options visible in the L1 picker, (b) the L1 wizard does not surface a "render timed out" before render completion (validates the L1 poll timeout is sized correctly per the "L1 wizard poll timeout" assumption in spec.md).
- [ ] T020 Open PR for branch `019-longform-10min-fix` with body referencing: spec 019, the affected Agent Modes (Mode 3 and Mode 4), and the relevant Master Spec sections (Mode 3 / Mode 4 contracts, retention/asset model). Constitution §Development Workflow.

---

## Dependencies & Story Order

```
T001 (deps unchanged)
  │
T002 (FFmpeg available) ──► T009 (ffmpeg integration test)
                            T013 (ffmpeg-built fixture)
T003, T004 (foundational) ──► all US tasks
                                    │
                                    ├─► US1: T005 → T006 → T007
                                    │
                                    ├─► US2: T008, T009 [P] → T010 → T011
                                    │
                                    └─► US3: T012, T013 [P] → T014 → T015
                                                                                    │
                                                                                    ▼
                                                                       T016 (pytest gate)
                                                                       T017, T018 [P]
                                                                       T019 (smoke tests)
                                                                       T020 (PR)
```

User stories US1 / US2 / US3 are fully independent and their phases (3 / 4 / 5) can be worked in parallel after the Foundational phase checkpoint. Within each phase, items marked [P] can run in parallel; non-[P] items have either a strict ordering or share a file.

## Parallel execution examples

- **US2 tests in parallel**: `T008 [P]` (mocked unit tests, no FFmpeg) + `T009 [P]` (FFmpeg integration test). Different files, no shared state.
- **US3 tests in parallel**: `T012 [P]` (parametrised MIME table) + `T013 [P]` (real WebM + MKV round-trip). Same test file but separate test methods — pytest runs them independently.
- **Polish phase parallel**: `T017` (debt doc) + `T018` (commit subject audit) — read-only, different files.

## MVP scope

The constitution-mandated minimum to ship:

- US1 + T005 + T006 + T007 + T016 — confirms the cap raise is correct and tested.

US2 and US3 ship together with US1 because they were committed together on this branch; splitting them into separate PRs at this point would re-do work for no gain. The PR (T020) bundles all three stories.

## Format validation

All 20 tasks use the strict checklist format `- [ ] T### [marker?] [story?] description with file path`. Every implementation task names an exact file path. Every test task names an exact test file. Every [shipped] task references an exact commit SHA for verification.

---

## Appendix: Cross-layer dependencies (out of L3 scope)

These changes ship from sibling repos and are not exercised by this repo's `pytest`. Listed here for PR-review traceability per Constitution §Development Workflow. They have no L3 task ID — verification is owned by the originating repo's own SpecKit feature.

- **L2** (`visualai-orchestration`) — paired with US1: `_VALID_DURATIONS`, `_MAX_SCRIPT_WORDS`, and `shot_count` formula must include the 480 / 600-second cases so a 10-min request from the wizard isn't rejected at L2 before reaching L3.
- **L1** (`visualai-frontend`) — paired with US1: duration picker shows 8-min and 10-min options; `POLL_TIMEOUT_MS` is 75 minutes (was 40). Aligns with the "L1 wizard poll timeout" assumption in spec.md. End-to-end verification rolled into Journey A of T019.
- **L1** (`visualai-frontend`) — paired with US3: the `<MediaRecorder>` capture path emits a codec-suffixed MIME (Chromium VP8, Firefox VP9) that flows through to L3's parameter-stripping rule (FR-008). End-to-end verification rolled into Journey C of T019.
