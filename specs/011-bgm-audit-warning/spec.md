# Feature Specification: BGM Mixing Failure Warning

**Feature Branch**: `011-bgm-audit-warning`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "Silent-fallback on BGM mixing failure inherited from upstream video.py. Documented in spec §Edge Cases; addressed when Step 3's mode registry rewrites the audio path. Create a warning."

## Overview

Close the v1 limitation explicitly carried forward from spec 010: when the upstream MPT pipeline at `app/services/video.py:546-557` silently falls back to voiceover-only output on a BGM mixing failure, the creator currently has no way to know their music wasn't applied. The render appears to succeed; the wizard reports "complete"; the My Assets card looks normal. The only signal is buried in the server logs as `failed to add bgm: <reason>`. This is the worst kind of failure mode for a creative tool: the user gets a polished output that doesn't match what they asked for.

This feature surfaces those failures to the user as **warnings** without editing `app/services/video.py` (Principle II keeps upstream MoviePy assembly code rebase-clean). The mechanism is observational: register an additional loguru sink at app startup that filters for the `failed to add bgm` log pattern, extracts the task id from the surrounding context, and persists a per-task sidecar file (`storage/tasks/<task_id>/bgm_failed.json`) recording the failure. The frontend's `/api/history` reads the sidecar; the wizard's progress UI surfaces a warning post-completion; the My Assets card carries a "music skipped" badge.

This is **purely additive** — no edits to `video.py`, `schema.py`, or `task.py`. The sink registers from a new VisualAI-only file; the sidecar writer lives there too. When Step 3's mode registry eventually rewrites the audio path with proper typed errors, this audit shim becomes redundant and can be removed in a single commit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Creator sees a clear warning when their music didn't apply (Priority: P1)

A creator picks a custom uploaded MP3 in the wizard, submits, and waits for the render. Internally, the upload is corrupted in a way the upload validator missed (e.g., a partially-truncated file that ffprobe accepts but moviepy can't read). The pipeline produces a final MP4 with voiceover and Pexels B-roll, but no music. Today: the wizard says "complete!" and the creator wonders why the music isn't there until they ask in support. With this feature: the wizard says "complete with a warning — music couldn't be applied to this render. The video plays voiceover-only. Try a different track or re-upload." The creator either retries with a different file or accepts the voiceover-only output knowingly.

**Why this priority**: this is the entire reason the feature exists. Silent failures in a creative tool destroy trust. Without P1, every user who hits a music failure thinks the whole product is buggy.

**Independent Test**: simulate a BGM mixing failure (e.g., point `bgm_file` at a file that exists but isn't a valid audio container, OR pre-corrupt one). Trigger a render. The wizard's completion state MUST display a warning naming the missing music; the rendered MP4 MUST exist with voiceover + Pexels but no BGM. The bare-minimum behavior is one visible warning string in the wizard.

**Acceptance Scenarios**:

1. **Given** a creator submitted a render with `bgm_type=file` and a bad `bgm_file` path that passes upload validation but fails at mix time, **When** the render completes, **Then** the wizard's completion state shows a "music couldn't be applied" warning with a one-line reason (e.g., "uploaded file is corrupt"), the MP4 plays voiceover-only, and the creator has explicit retry / accept options.
2. **Given** a creator submitted a render with `bgm_type=random` and a transient I/O failure prevents the random track from loading, **When** the render completes, **Then** the same warning surfaces — but the message names "the random bundled track" rather than "your uploaded file."
3. **Given** a successful render where BGM mixed cleanly, **When** the wizard reaches completion, **Then** no music-related warning is shown and the existing complete state is byte-equivalent to today's behavior (zero regression).
4. **Given** the creator picked `bgm_type=""` (None mode) and the render completed, **When** the wizard reaches completion, **Then** no warning is shown — silence in the music track was the user's choice, not a failure.

---

### User Story 2 — My Assets retroactively flags renders that had music failures (Priority: P2)

A creator returns to My Assets a day later to find a particular video they remember submitting with a custom track. They want to know: "did the music get applied or not?" The card carries a small "music skipped" badge if the BGM mixing failed; absence of badge means the music applied (or was None). Hovering the badge surfaces the failure reason.

**Why this priority**: makes P1's warning durable beyond the wizard session. Without P2, the warning is shown once and lost on page refresh; the creator can't audit historical renders. Lower priority than P1 because the wizard warning catches it at the moment of failure for currently-active renders.

**Independent Test**: produce a render with a known BGM failure (per US1's Independent Test). Open My Assets in a fresh session. The corresponding card MUST show the "music skipped" badge with the documented hover text. Other cards (clean renders, None-mode renders) MUST NOT show the badge.

**Acceptance Scenarios**:

1. **Given** a render whose BGM mixing failed at render time, **When** the creator opens My Assets, **Then** the card shows a small "music skipped" badge with a tooltip explaining why.
2. **Given** a render whose BGM mixed cleanly, **When** the creator opens My Assets, **Then** no music-related badge appears on the card.
3. **Given** a render the creator submitted with None mode (deliberately no music), **When** they open My Assets, **Then** no music-related badge appears — None mode is not a failure, it's a choice.

---

### User Story 3 — Operator can audit BGM failure rate across all renders (Priority: P3)

The operator (founder) wants to know how often BGM mixing fails — a high rate indicates a systemic issue (corrupt bundled tracks, ffmpeg version drift, certain file formats consistently failing). The operator runs a simple shell command to count `bgm_failed.json` sidecars across all task folders.

**Why this priority**: low day-one value but cheap to support. The sidecar file format (introduced for P1's wizard warning) doubles as a queryable artifact for ops. No new code is required for P3 beyond what P1 ships.

**Independent Test**: with at least one failing render in `storage/tasks/`, run `find storage/tasks -name 'bgm_failed.json' | wc -l` and confirm the count matches the number of failed renders observed.

**Acceptance Scenarios**:

1. **Given** N renders have BGM failures recorded in their task folders, **When** the operator runs the shell aggregation, **Then** the count returned equals N.
2. **Given** the operator inspects an individual `bgm_failed.json`, **When** they `cat` the file, **Then** they see a JSON object with at least `{reason, bgm_file, timestamp}` — enough context to debug the underlying cause.

---

### Edge Cases

- **The mixing failure log line never fires** (e.g., MoviePy decides to silently produce a video with no audio for some other reason): out of scope for v1. The audit shim only catches the documented "failed to add bgm" pattern; other silent-output bugs remain undetected. Documented as known limitation.
- **The log line fires but the task_id can't be extracted** (e.g., the log was emitted from a thread that doesn't have the loguru bind context): the sidecar writer falls back to writing to a generic `storage/audit/bgm_failures.log` so the operator-side P3 view still sees the failure, even if the wizard's per-task warning misses it. This is degraded mode; should be rare.
- **Multiple failures for the same task** (one BGM failure caught + a second unrelated one): the sidecar file is written-once. Subsequent failures append to a `previous_failures` array in the same JSON. The wizard surfaces only the first failure to keep the UX simple.
- **The render itself fails (no `final-N.mp4` produced)**: the BGM failure is moot. The wizard's existing "render failed" state takes precedence; the music warning is suppressed since the user has bigger problems.
- **The creator picked None mode and a sidecar is somehow created**: this would indicate an instrumentation bug (the audit shim should only fire when a real BGM mix was attempted). The wizard MUST NOT show a warning when the creator's submitted state was `bgm_type=""` regardless of sidecar presence — the wizard cross-checks against the requested config.
- **The audit shim itself fails** (sidecar write fails, log filter misconfigured): the original silent-fallback behavior is preserved. The shim is best-effort instrumentation; its failure mode MUST NOT break renders that today work fine.
- **Spec 010's tests must continue to pass** with no modification — the audit shim is invisible to tests that don't specifically exercise failure modes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect every occurrence of the `failed to add bgm: <reason>` log emission in `app/services/video.py:556-557` without modifying `video.py` itself. Detection MUST be observational (loguru sink filtering or equivalent), not invasive.
- **FR-002**: When a BGM mixing failure is detected, the system MUST persist a sidecar file `storage/tasks/<task_id>/bgm_failed.json` containing at minimum: `{reason: string, bgm_file: string, timestamp: ISO-8601 string}`. If the task_id cannot be determined from log context, the system MUST fall back to a generic ops log at `storage/audit/bgm_failures.log` (operator-only view).
- **FR-003**: The frontend's `/api/history` route MUST read each task's `bgm_failed.json` sidecar (when present) and include a `bgm_failed` field in the history item shape. The field carries the failure reason; absence means no failure.
- **FR-004**: The wizard's progress UI MUST surface a clear, non-blocking warning when a render completes with a `bgm_failed` flag set. The warning text MUST: (a) name the issue ("music couldn't be applied to this render"); (b) state the consequence ("the video plays voiceover only"); (c) offer a retry option (regenerate with the same wizard inputs); (d) cite the underlying reason in human-readable form.
- **FR-005**: The My Assets card MUST display a small "music skipped" badge on any render whose `bgm_failed` flag is set. The badge MUST include hover/tooltip text with the failure reason.
- **FR-006**: When the creator's request used `bgm_type=""` (None mode), the wizard and My Assets MUST NOT display the music warning even if a sidecar file exists. None mode is not a failure.
- **FR-007**: The audit shim MUST be self-contained in a NEW VisualAI-only file (e.g., `app/services/bgm_audit.py`). It MUST NOT edit `app/services/video.py`, `app/services/task.py`, `app/models/schema.py`, or any other upstream-fork-surface file beyond what spec 010 already touched.
- **FR-008**: The audit shim MUST register its loguru sink at app startup. The registration call lives in either an existing fork-surface file already touched by spec 010 (acceptable: `app/router.py`) OR via a side-effect import at module load. New fork-surface touches are NOT permitted by this spec.
- **FR-009**: The audit shim MUST be best-effort: if its own logic raises (e.g., sidecar file write fails), the original render pipeline MUST proceed unaffected. The shim catches its own exceptions and logs them at WARNING level without propagating.
- **FR-010**: When the underlying upstream `video.py` BGM behavior is rewritten in Step 3 (mode registry), this entire feature MUST be removable in a single commit (sink unregistration + sidecar reader removal + frontend badge removal). The feature MUST leave no schema fingerprint or migration debt.
- **FR-011**: Renders that today produce clean BGM mixing MUST be byte-equivalent in their pipeline output AND in their `/api/history` response shape AFTER the audit shim is installed (zero regression for the happy path).

### Key Entities

- **BGM Failure Sidecar**: a JSON file at `storage/tasks/<task_id>/bgm_failed.json` written when BGM mixing fails for that task. Fields: `reason` (the underlying error string), `bgm_file` (the requested file path that failed), `timestamp` (ISO-8601 of when the failure was recorded). Read-once by the frontend's `/api/history`; never updated after creation (write-once contract).
- **Audit Loguru Sink**: a function registered with loguru at app startup that filters every log message for the `failed to add bgm` pattern and routes matches to the sidecar writer. Pure observer — does not modify the log stream and does not affect other sinks (stdout, future file logs).
- **Sidecar Reader** (extension to existing entity): the `/api/history` route's per-task scan gains one new check — read `bgm_failed.json` if present, attach to the history item, leave absent otherwise. No changes to the existing `script.json` or render-artifact reads.
- **Wizard Warning State** (new wizard UI state): when the wizard's polled task data carries a `bgm_failed` flag, render the warning UI element. Cleared on retry or on closing the wizard. Not persisted client-side.
- **My Assets Badge**: a small visual indicator on cards whose `bgm_failed` flag is set. Same visual weight as the existing "no audio" / "failed" badges (consistent with spec 001's badge conventions).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of synthetic BGM-mixing-failure scenarios MUST produce a visible wizard warning. Verified by inducing a failure (corrupting a task's `bgm_file` between submission and render, OR pointing `bgm_file` at a known-bad file) and confirming the wizard reaches a completion state that includes the warning text.
- **SC-002**: 100% of clean BGM renders (no failure) MUST produce ZERO music-related warnings in the wizard or My Assets. Verified by running the existing spec 010 smoke tests and confirming no UI regression.
- **SC-003**: The shim adds ≤ 50 ms to total render time on a 30 s 9:16 video. Measured by timing 5 matched-pair renders with vs without the audit shim active. Practical reasoning: a loguru sink filter is cheap; only sidecar-write incurs measurable I/O, and only on the rare failure path.
- **SC-004**: The "music skipped" badge appears within 10 s of My Assets first render after a known-failed task. Measured by submitting a failing render, opening My Assets, and timing badge appearance.
- **SC-005**: The operator's aggregation command (`find storage/tasks -name 'bgm_failed.json' | wc -l`) returns a count exactly matching the number of distinct failed renders observed in the test window. Verified by deliberately failing N renders and confirming the count.
- **SC-006**: When this entire feature is removed in a future commit (per FR-010), the project's behavior MUST be byte-equivalent to a state where this feature was never installed. Verified by `git revert` of the entire feature commit and re-running spec 010's test suite — no test failures, no schema differences, no migration to undo.

## Assumptions

- **MPT's loguru log line at `app/services/video.py:557` continues to fire on every BGM mixing failure.** This is the observable signal the entire feature depends on. If a future MPT rebase removes or renames the log line, this feature breaks silently — the audit shim's tests would catch the regression on the next test run.
- **The task_id is reliably present in the loguru bind context when `combine_videos` runs.** If MPT's `task.py` stops binding `task_id` to its loguru context, the per-task sidecar attribution degrades to the operator-only fallback. Verified by inspecting `app/services/task.py`'s existing logging — `task_id` is bound throughout.
- **The render happy path is the overwhelming majority of cases.** Audit shim cost is bounded by the failure rate; even at 1% failure rate, the sidecar write fires rarely enough that per-render overhead is negligible.
- **The wizard's existing polling loop (poll `/api/status/<task_id>` every 2 s) is the right surface for the warning.** When `final-N.mp4` exists AND `bgm_failed.json` exists, the wizard's "complete" state augments to "complete with warning." No new polling endpoint required.
- **None mode + sidecar file should never co-occur in normal operation.** If they do, the wizard cross-checks the original `bgm_type` from the task's `script.json` and suppresses the warning. This is defense-in-depth; the audit shim itself is designed to only fire when a real mix was attempted.
- **The feature is bounded to BGM failures specifically.** Other silent-output failures (subtitle render fails, voiceover synthesis silently produces empty audio, etc.) are NOT in scope for this spec. Each future audit needs its own narrow shim.
- **No multi-tenant scoping at v1.** Sidecar files share `storage/tasks/<task_id>/` — same shared infrastructure spec 010 uses. When debt #2 repays in Step 2, sidecars scope per-tenant via the same path-rewrite that other artifacts inherit.

## Dependencies

- **Spec 010 is shipped** (it is, as of 2026-05-02). This feature only matters when creators have actually configured music — which is the post-spec-010 world.
- **The upstream `app/services/video.py:546-557` BGM mixing block continues to use the documented log message format.** Tested by parsing the log message at audit-shim-load time and asserting it matches the expected pattern.
- **No DB or external service.** Sidecar files are local-filesystem; loguru sinks are in-process; the wizard reads via the existing `/api/history` route.

## Constitutional Impact

| Principle | Impact | Mitigation |
|---|---|---|
| **I. Layer 3 Scope** | None — purely render-engine instrumentation; no user / billing logic added. | n/a |
| **II. Surgical Fork Discipline** | Touches **fork-surface** `app/router.py` (one new line registering the audit module's import side-effect — same file already touched by spec 010). Adds **new VisualAI-only file** `app/services/bgm_audit.py`. **Does NOT touch** `app/services/video.py`, `app/services/task.py`, or `app/models/schema.py`. The whole feature is removable in one commit (FR-010). | Documented in §Dependencies + FR-010. |
| **III. Multi-Tenant Context Propagation** | Sidecar files land in shared `storage/tasks/<task_id>/` without tenant scoping — continuation of debt #2. | Piggybacks on existing #2; no new debt. |
| **IV. External Asset Acceptance** | None — no external APIs. The audit shim is purely in-process. | n/a |
| **V. Mode-Aware Rendering Contract** | When the Step 3 mode registry rewrites the audio path with proper typed errors, this feature becomes redundant and should be removed (FR-010). The shim is a temporary scaffold. | Removal is deliberately one-commit-clean per FR-010. |

**Net constitutional impact**: zero new debts. One existing debt (#2) gains one more burndown task. Feature is explicitly designed to retire cleanly when Step 3 lands.

## Cross-references

- [Spec 010 — Music Track Control + Custom Uploads](../010-music-control/spec.md) — this spec resolves spec 010's documented v1 limitation (silent BGM mixing failure) without violating Principle II.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle II (Surgical Fork Discipline) is the constraint that makes this an observational shim rather than a `video.py` edit.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — debt #2 (multi-tenant scoping on uploads) gains one more burndown task via this feature.
- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md) — Step 3 will obsolete this shim when the audio path moves into the mode registry.
- [`app/services/video.py:546-557`](../../app/services/video.py#L546-L557) — the upstream silent-fallback this feature observes without modifying.
