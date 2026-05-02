---
description: "Task list for feature 013 — Polish Mode for Script Editor"
---

# Tasks: Polish Mode for Script Editor

**Input**: Design documents from `/specs/013-script-polish-mode/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Smoke + integration tests are MANDATORY. The contracts in `contracts/` define **31 acceptance tests** total (10 PL + 10 WS + 11 WMS). Backend uses pytest (already set up by spec 010); frontend uses Vitest (already set up by spec 012).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. Spec.md's three user stories:

- **US1** (P1): Polish-mode end-to-end — creator brief → polished hook/body/CTA marketing script
- **US2** (P2): Mode selector clarity + state persistence
- **US3** (P3): Legacy compat — script_mode-omitted callers behave byte-equivalent to today

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- All file paths are project-relative (MPT for backend; `visualai-frontend/` for Layer 1)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: minimal — toolchain already established by specs 010 (pytest) + 012 (vitest + MSW). No new deps.

- [ ] T001 Confirm `test/services/test_helpers.py` (created by spec 010) is on disk + importable. Path: `test/services/test_helpers.py`. (Idempotent check; should already exist.)
- [ ] T002 [P] Confirm `visualai-frontend/vitest.config.ts` + `visualai-frontend/tests/setup.ts` (created by spec 012) are on disk + working. Run `pnpm vitest run` in `visualai-frontend/` and verify it exits 0 (or with "no tests for this feature yet"). Path: `visualai-frontend/vitest.config.ts` + `visualai-frontend/tests/setup.ts`. (Idempotent check.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared types + skeletons that every user story depends on. Once Phase 2 completes, US1 / US2 / US3 can each be developed in parallel.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Backend (Layer 3)

- [ ] T003 Add two new optional fields to `VideoParams` in `app/models/schema.py`: `script_mode: Optional[Literal["auto", "verbatim", "polish"]] = None` and `script_brief: Optional[str] = None`. Place them next to the existing `video_script` field. Per [data-model.md §Entity 1 + §Entity 2](./data-model.md). Path: `app/models/schema.py`.
- [ ] T004 Refactor `app/services/task.py:generate_script()` to use the dispatch matrix from [contracts/script-mode-wire-shape.md §Backend dispatch](./contracts/script-mode-wire-shape.md): polish branch first (raises NotImplementedError as a placeholder until T010); then verbatim/legacy fall-through; then auto/legacy. Confirm legacy callers (script_mode=None, empty/non-empty video_script) produce IDENTICAL behavior to today. **No `polish_script` call yet** — the polish branch exists but raises until T010 lands. Path: `app/services/task.py`.

### Frontend (Layer 1)

- [ ] T005 [P] Create `visualai-frontend/src/lib/script-mode.ts` with all TypeScript types from [data-model.md §Entity 3](./data-model.md): `ScriptMode`, `WizardScriptState`, `ScriptParams`, `PRISTINE_SCRIPT`. Plus the helpers `scriptStateToParams(state)` and `isPristineScript(state)`. Path: `visualai-frontend/src/lib/script-mode.ts`.
- [ ] T006 Extend the wizard's `/api/generate` proxy at `visualai-frontend/src/app/api/generate/route.ts` to pass through `script_mode` + `script_brief` (alongside the existing `video_subject`/`video_script`/`music`/etc. fields). Conditional inclusion: only include `script_mode` if non-null. Path: `visualai-frontend/src/app/api/generate/route.ts`. (Depends on T005 for types.)

### Verification (foundational tests)

- [ ] T007 [P] Vitest tests for `script-mode.ts` helpers — covers WMS-10 (`scriptStateToParams` for all 3 modes) and WMS-11 (`isPristineScript` correctness across mode/text combinations). Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.
- [ ] T008 [P] pytest tests for the legacy-compat dispatch — covers WS-1 (`script_mode=None` + empty `video_script` → auto path) and WS-2 (`script_mode=None` + non-empty `video_script` → verbatim path). Mock `llm.generate_script` to assert it was called (or NOT called) per the matrix. Path: `test/services/test_polish_script.py`.

**Checkpoint**: Foundation ready. Schema fields exist, frontend types + helpers compile, dispatch refactor preserves legacy behavior, /api/generate forwards new fields. All three user stories can begin in parallel.

---

## Phase 3: User Story 1 — Polish-Mode End-to-End (Priority: P1) 🎯 MVP

**Goal**: A creator pastes a rough brief in Polish mode, the LLM rewrites it as a hook → body → CTA marketing script, the rendered MP4 voiceover speaks the polished version (NOT the brief). Both brief and polished script are persisted in `task.json` for provenance.

**Independent Test**: Submit two renders with the same brief — once Polish, once Verbatim. Polish render's voiceover MUST differ structurally from the brief; Verbatim render's voiceover MUST match word-for-word. `script.json` MUST contain both `script_brief` (original) and `video_script` (polished output) for the Polish render. Per SC-001 + SC-002.

### Tests for User Story 1

- [ ] T009 [P] [US1] pytest tests PL-1, PL-2, PL-7, PL-9, PL-10 — happy-path `polish_script` calls. Mock `_generate_response` to return synthetic polished prose. Assert: returns non-empty; contains no markdown artifacts; prompt has correct `target_words` for each duration. Path: `test/services/test_polish_script.py`.
- [ ] T010 [P] [US1] pytest tests PL-3, PL-4, PL-6, PL-8 — `polish_script` validation/error paths. Empty brief → `ValueError`; whitespace-only brief → `ValueError`; LLM mock returns empty → `ValueError("empty polish output")`; language=es with English brief → prompt contains the language constraint. Path: `test/services/test_polish_script.py`.
- [ ] T011 [P] [US1] pytest test PL-5 — propagation: when `_generate_response` raises `RuntimeError`, `polish_script` does NOT swallow; the exception propagates upward. Path: `test/services/test_polish_script.py`.
- [ ] T012 [P] [US1] pytest tests WS-7, WS-8, WS-9, WS-10 — polish dispatch in `task.py:generate_script`. WS-7: polish + valid brief → `params.video_script` overwritten with polished output, `params.script_brief` retains original. WS-8: polish + empty brief → task fails with `error="polish_brief_required"`. WS-9: LLM mock raises → task fails with `error="polish_failed"`. WS-10: polish prompt contains BOTH the brief AND the enriched subject (Q1 verification). Path: `test/services/test_polish_script.py`.
- [ ] T013 [P] [US1] Vitest test WMS-6 — Polish mode + empty textarea + Submit click → inline error within 100 ms; submit handler NOT called. Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.
- [ ] T014 [P] [US1] Vitest test WMS-9 — Polish mode + valid brief + Submit click → submit handler called with `{script_mode: "polish", video_script: <brief>, script_brief: <brief>}`. Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.

### Implementation for User Story 1

- [ ] T015 [US1] Implement `polish_script(brief, video_subject, duration_seconds, language)` function in `app/services/llm.py` per [contracts/polish-llm-contract.md](./contracts/polish-llm-contract.md). Place next to the existing `generate_marketing_script` function (~line 591). Use the prompt template verbatim from the contract. Use `_generate_response` for the LLM call (existing helper). Strip `*` and `#` markdown artifacts from output. Raise `ValueError("polish_brief_required")` on empty brief; raise `ValueError("empty polish output")` on empty LLM response. Path: `app/services/llm.py`.
- [ ] T016 [US1] Replace the `NotImplementedError` placeholder in `app/services/task.py:generate_script()`'s polish branch (from T004) with the real dispatch: when `script_mode == "polish"`, validate brief non-empty (else `polish_brief_required`), call `llm.polish_script(brief=video_script, video_subject=params.video_subject or "", duration_seconds=20, language=params.video_language or "en")`, catch any exception → `polish_failed`, overwrite local `video_script` variable with the polished output. Path: `app/services/task.py`. (Continues debt #5.)
- [ ] T017 [US1] In `visualai-frontend/src/app/modes/short-video/page.tsx`'s `ShortVideoWizard`, add `script` state (`useState<WizardScriptState>(PRISTINE_SCRIPT)`) and pass `script` + `setScript` down to the `StepScriptVoice` component. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`.
- [ ] T018 [US1] In `StepScriptVoice` (or a new `MusicAndScriptPanel` if simpler), conditionally render the textarea based on `script.mode`. When mode is `"polish"` or `"verbatim"`, show textarea with mode-specific placeholder. When mode is `"auto"`, hide textarea entirely. Wire `onChange` to `setScript({ ...script, text: e.target.value })`. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T017.)
- [ ] T019 [US1] Update the wizard's `submit()` handler to call `scriptStateToParams(script)` and merge the result into the `/api/generate` request body. Add inline validation: if `script.mode === "polish"` and `script.text.trim().length === 0`, set an inline error and return early without calling fetch. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T017 + T005.)
- [ ] T020 [US1] In `StepGenerate` (the Step 4 component), surface the typed errors from `task.error`: when `error === "polish_brief_required"`, show "Polish mode needs a brief — go back to Step 3 and type something" + a "Back to Step 3" button. When `error === "polish_failed"`, show "We couldn't polish that brief — try again, or switch to Verbatim to use it as-is" + two buttons: "Try again with Polish" (resubmits) and "Switch to Verbatim" (sets `script.mode = "verbatim"` + navigates back to Step 3). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T017.)
- [ ] T021 [US1] Run [quickstart.md Part 2](./quickstart.md) manual end-to-end verification: paste a real product URL in Step 1; switch to Polish mode in Step 3 with a real brief; verify the rendered MP4's voiceover is structurally hook/body/CTA + mentions specific brief facts; verify `script.json` has both `script_brief` (original) and `video_script` (polished). Repeat for 5 different briefs to spot-check SC-001's 50% rewrite threshold. Path: manual verification.

**Checkpoint**: User Story 1 fully functional. Polish mode works end-to-end. MVP delivered.

---

## Phase 4: User Story 2 — Mode Selector Clarity + State Persistence (Priority: P2)

**Goal**: The 3-mode selector is visible at first paint, mode-switch updates the textarea + helper text immediately, state persists across forward/back wizard navigation.

**Independent Test**: All three pills visible on Step 3 first paint with one-line descriptions. Clicking a pill flips the active state immediately. Picking Auto hides the textarea; switching back reveals previously-typed text. Navigating Step 3 → Step 1 → Step 3 preserves the mode + text. Per WMS-1..WMS-5.

### Tests for User Story 2

- [ ] T022 [P] [US2] Vitest tests WMS-1, WMS-2, WMS-3, WMS-4 — initial state is Auto; clicking each pill flips `state.mode`; clicking Auto hides textarea but preserves `state.text`. Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.
- [ ] T023 [P] [US2] Vitest test WMS-5 — typing in Verbatim → switching to Auto → switching back to Verbatim or Polish → text reappears unchanged. Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.
- [ ] T024 [P] [US2] Vitest test WMS-7 — Verbatim mode + empty text + Submit click → inline error appears; submit NOT called (matches WMS-6 pattern but for Verbatim). Path: `visualai-frontend/tests/wizard-mode-selector.test.ts`.
- [ ] T025 [P] [US2] pytest tests WS-3, WS-4, WS-5 — explicit dispatch matrix rows: `{script_mode: "auto", video_script: ""}` → auto path; `{script_mode: "auto", video_script: "ignored"}` → auto path (script ignored); `{script_mode: "verbatim", video_script: "x"}` → verbatim. Path: `test/services/test_polish_script.py`.

### Implementation for User Story 2

- [ ] T026 [US2] Build the 3-pill mode selector row at the top of `StepScriptVoice` per [contracts/wizard-mode-selector-contract.md §Visual layout](./contracts/wizard-mode-selector-contract.md). Three buttons (Auto / Verbatim / Polish), Tailwind classes mirroring the Music panel's pill style from spec 010. Click handlers update `script.mode` via `setScript`. ARIA: `role="radiogroup"` on the container + `role="radio"` + `aria-checked` on each pill. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`.
- [ ] T027 [US2] Add mode-specific helper text below the textarea (Auto: "Leave empty — the AI will write a script…"; Verbatim: "Your text will be read verbatim as the voiceover."; Polish: "Type a rough brief — the AI will rewrite it as a 20-second hook → body → CTA."). Use `aria-describedby` to associate the helper text with the textarea. Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T026.)
- [ ] T028 [US2] Add inline-error rendering for Verbatim+empty validation (mirrors the Polish+empty error pattern from T019 but with different copy). Path: `visualai-frontend/src/app/modes/short-video/page.tsx`. (Depends on T019.)
- [ ] T029 [US2] Run [quickstart.md Part 3, Part 4, Part 7](./quickstart.md) manual end-to-end: verify Verbatim mode produces word-for-word voiceover; verify Auto mode hides textarea + produces LLM-generated script; verify mode + text persist across Step 3 → Step 2 → Step 3 navigation. Path: manual verification.

**Checkpoint**: User Story 2 complete. All three modes are usable, the selector is clear, state persists. Both US1 (Polish) and US2 (selector UX) work independently.

---

## Phase 5: User Story 3 — Legacy Compat for script_mode-omitted Callers (Priority: P3)

**Goal**: Direct curl callers (and any non-VisualAI integration) submitting requests WITHOUT `script_mode` see byte-equivalent behavior to today's pre-spec-013 pipeline.

**Independent Test**: Two curl requests — one with empty `video_script` and no `script_mode`; one with non-empty `video_script` and no `script_mode`. Both produce voiceover identical to today's auto/verbatim paths. Per SC-003 + WS-1 + WS-2.

### Tests for User Story 3

(Already covered by T008 in Phase 2 — WS-1 + WS-2 are the legacy-compat dispatch tests, scheduled there because they're foundational regression guards. No additional tests in Phase 5.)

### Implementation for User Story 3

(No code changes needed — Phase 2's `task.py` refactor (T004) preserves legacy behavior by design. Phase 5 is verification-only.)

- [ ] T030 [US3] Run [quickstart.md Part 1](./quickstart.md) manual end-to-end: two curl requests omitting `script_mode`; verify both renders produce voiceover identical to today's pipeline (legacy auto path + legacy verbatim path). Confirm `task.json` for both has `script_mode: null` and `script_brief: null`. Path: manual verification.

**Checkpoint**: User Story 3 verified. Legacy callers unaffected. SC-003 satisfied.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: tasks that span multiple stories or finalize the feature for merge.

- [ ] T031 [P] Update `STEP1_DEBT.md` to note that spec 013 added a 3rd touch line to `app/services/task.py` (continues debt #5) and continues debt #4 (Mode 2 polish prompt inline in `llm.py`). Path: `STEP1_DEBT.md`.
- [ ] T032 [P] Run the full backend test suite: `pytest test/services/test_polish_script.py -v`. Expected: 17 tests pass (PL-1..PL-10 + WS-1..WS-10 except WS-6 which is wizard-only). Total wall clock < 5 s. Path: manual verification.
- [ ] T033 [P] Run the full frontend test suite: `pnpm vitest run` in `visualai-frontend/`. Expected: 11 polish-mode tests (WMS-1..WMS-11) pass plus the existing tests from specs 010 + 012 still pass. Path: manual verification.
- [ ] T034 [P] Run [quickstart.md Part 5, Part 6, Part 9](./quickstart.md): polish empty-brief refusal + polish_failed surfacing + cross-spec composition with URL scraping. Path: manual verification.
- [ ] T035 [P] Run [quickstart.md Part 8](./quickstart.md) provenance shell command — list all polished renders + diff their briefs vs polished outputs. Confirms `script_brief` is being persisted across real renders. Path: manual verification.
- [ ] T036 Run [quickstart.md Part 10](./quickstart.md) — final constitution compliance check. `git diff --stat origin/main..HEAD -- 'app/services/material.py' 'app/services/voice.py' 'app/services/video.py'` MUST show ZERO changes. If any of those three files changed, abort merge — the implementation violates Principle II. Path: manual verification.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. Start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. **BLOCKS all user stories.**
- **User Stories (Phase 3+)**: All depend on Phase 2 completion.
  - US1 (P1) is the MVP. Ship + validate before moving to US2 / US3.
  - US2 (P2) builds on US1's wizard scaffolding (T017) but adds the pill row + helper text.
  - US3 (P3) is verification-only — no new code; tests live in Phase 2.
- **Polish (Phase 6)**: depends on all desired user stories being complete.

### Within Each User Story

- Tests MUST exist and FAIL before implementation (constitution-aligned discipline).
- T015 (`polish_script` function) before T016 (dispatch wiring).
- T017 (parent state) before T018, T019, T020 (consumers of that state).
- T026 (pill row UI) before T027 (helper text) and T028 (inline error rendering).

### File Conflicts to Note

| File | Tasks touching it | Sequential? |
|---|---|---|
| `app/services/llm.py` | T015 | Single task; no conflict |
| `app/services/task.py` | T004, T016 | **Sequential** — T016 replaces T004's placeholder |
| `app/models/schema.py` | T003 | Single task |
| `visualai-frontend/src/app/modes/short-video/page.tsx` | T017, T018, T019, T020, T026, T027, T028 | **All sequential** (same file) |
| `visualai-frontend/src/lib/script-mode.ts` | T005 | Single task |
| `visualai-frontend/src/app/api/generate/route.ts` | T006 | Single task |
| `test/services/test_polish_script.py` | T008, T009, T010, T011, T012, T025 | Different test functions; can be developed `[P]` because pytest collects each independently |
| `visualai-frontend/tests/wizard-mode-selector.test.ts` | T007, T013, T014, T022, T023, T024 | Different test functions; can be developed `[P]` |
| `STEP1_DEBT.md` | T031 | Single task (small edit) |

### Parallel Opportunities

- **Phase 1**: T001 + T002 in parallel (different files, both idempotent confirmations).
- **Phase 2**: T003 (schema) + T005 (lib) in parallel; T004 (task.py refactor) sequential after T003 (depends on schema field for the dispatch); T006 (API proxy) parallel with T004; T007 + T008 parallel test development.
- **Phase 3 tests (T009–T014)**: ALL `[P]` — different test functions, independent of each other.
- **Phase 3 implementation**: T015 first; T016 sequential after T015; T017–T020 sequential within `page.tsx`.
- **Phase 4 tests (T022–T025)**: ALL `[P]`.
- **Phase 4 implementation**: T026 → T027 → T028 sequential within `page.tsx`.
- **Phase 6**: T031, T032, T033, T034, T035 all `[P]`; T036 sequential (final compliance check).

---

## Parallel Example: Phase 3 Tests

```bash
# Six test tasks can be developed in parallel:
Task: "PL-1, PL-2, PL-7, PL-9, PL-10 happy-path polish_script tests in test/services/test_polish_script.py"
Task: "PL-3, PL-4, PL-6, PL-8 polish_script validation tests in test/services/test_polish_script.py"
Task: "PL-5 polish_script exception propagation test in test/services/test_polish_script.py"
Task: "WS-7, WS-8, WS-9, WS-10 polish dispatch tests in test/services/test_polish_script.py"
Task: "WMS-6 Polish empty-brief inline validation in tests/wizard-mode-selector.test.ts"
Task: "WMS-9 Polish submit-handler test in tests/wizard-mode-selector.test.ts"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1: Setup (T001, T002).
2. Complete Phase 2: Foundational (T003–T008). **CRITICAL — blocks all stories.**
3. Complete Phase 3: User Story 1 (T009–T021).
4. **STOP and VALIDATE**: run [quickstart.md Part 2](./quickstart.md). Confirm SC-001 across 5 briefs.
5. Demo / merge as PR if ready.

### Incremental Delivery

1. Setup + Foundational → Foundation ready (~30 min).
2. US1 Polish path → ~1.5 hours (LLM function + dispatch + wizard polish UI + 14 tests).
3. US2 Mode selector UX → ~45 min (pill row + helper text + persistence + 5 tests).
4. US3 Legacy compat verification → ~10 min (manual quickstart Part 1).
5. Polish → ~30 min (STEP1_DEBT + full test runs + constitution compliance check).

**Total estimated time**: ~3 hours single-developer, single-session.

### Constitution Compliance Reminders

- **Do not edit `app/services/material.py`, `voice.py`, `video.py`** (Principle II). T036 verifies via `git diff --stat`.
- The PR description for this feature MUST cite Mode 2 (Short Marketing Video) and Master Spec §3 (Five Agent Modes) per the constitution's §Development Workflow rule for fork-surface PRs (touches `schema.py`, `llm.py`, `task.py`).
- The 31 acceptance tests are a hard merge gate. T032 + T033 verify them.

---

## Notes

- `[P]` tasks = different files OR different test functions; can run in parallel.
- `[Story]` label maps task to specific user story for traceability and independent delivery.
- Each user story is independently completable + testable. Halting after US1 ships a real MVP.
- The 31 acceptance tests are scheduled across:
  - Phase 2 (Foundational): T007 (WMS-10, WMS-11) + T008 (WS-1, WS-2) — 4 tests
  - Phase 3 (US1): T009 (5 PL) + T010 (4 PL) + T011 (1 PL) + T012 (4 WS) + T013 (1 WMS) + T014 (1 WMS) — 16 tests
  - Phase 4 (US2): T022 (4 WMS) + T023 (1 WMS) + T024 (1 WMS) + T025 (3 WS) — 9 tests
  - Phase 5 (US3): no new tests — already covered by T008 in Phase 2
  - Phase 6: 0 new tests; just full-suite runs (T032, T033)
  - **Total: 4 + 16 + 9 + 0 + 0 = 29 of 31** acceptance tests scheduled. The 2 unscheduled (WMS-8 — auto submit; WS-6 — wizard-prevented case) are implicitly covered by T008's foundational legacy-compat tests + T026's pill row implementation. Add them to Phase 4 if explicit coverage is desired.
- Commit after each task or logical group. The full feature is one PR per the SpecKit governance pattern; intra-feature commits are encouraged for review-ability.
- This feature is parallel-deliverable with specs 002 (duration — pending), 009 (overlays — pending), 011 (BGM audit — pending). All four touch the wizard's `page.tsx` in different JSX subtrees — merge order is mechanical only.
