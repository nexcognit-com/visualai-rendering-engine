# Feature Specification: Polish Mode for Script Editor

**Feature Branch**: `013-script-polish-mode`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "Polish mode for the wizard's script editor — add a third mode (Auto / Verbatim / Polish) so creators can paste a rough brief or bullet points and have the LLM rewrite it into a hook → body → CTA marketing script. Resolves the 'AI didn't reinvent the script' gap discovered when the user typed a prompt and got their text back verbatim as the voiceover."

## Overview

Today the wizard's Step 3 script editor has exactly two behaviors: leave it empty and the LLM writes a script from the subject; fill it and your text becomes the voiceover verbatim. The placeholder text honestly says "leave empty for AI-generated," but real-world testing surfaced a third expectation creators have — they want to paste a *rough brief or bullet points* and have the AI **polish** that into a hook → body → CTA marketing script, not have it taken as the final words.

This feature adds that third mode: **Polish**. The wizard's script editor gains a mode selector — Auto / Verbatim / Polish — and a new LLM function turns the creator's brief into proper marketing copy. The existing two modes are preserved unchanged for backwards compatibility (creators with the old reflexes still work). The selector is the only new UI; everything else flows through the same render pipeline.

This was the second user-visible gap (after URL scraping in spec 012) where the wizard quietly mismatched creator expectations. Like spec 012, the fix is honest UX: name the modes, show the selector, route accordingly. No more silent reinterpretation.

## Clarifications

### Session 2026-05-02

- Q: How does Polish mode interact with the URL-scraped enriched subject? → A: **Brief primary + enriched subject as factual context.** The polish prompt receives both — the brief drives creative direction, the enriched subject grounds the LLM in real product facts. Prompt structure: "Brief: {brief}. Product context: {subject}. Polish into hook/body/CTA, prioritizing brief." When `video_subject` is empty / non-URL-derived, fall back to brief-only (no synthetic context).
- Q: How is the brief preserved in the task's persisted data? → A: **Store both brief + polished script.** New optional `script_brief: Optional[str]` field on `VideoParams` mirrors how `video_script` is stored. `task.json`'s params section gains the brief alongside the polished `script` field. Enables provenance ("did the AI change my key fact?"), debug ("brief vs output comparison"), and future regenerate-with-different-tone flows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Creator pastes a brief and gets polished marketing copy (Priority: P1)

A marketer types a few rough lines into the script editor — bullet points, a stream-of-consciousness pitch, or a half-finished sentence. They pick **Polish** as the script mode and submit. The rendered MP4's voiceover is a clean hook → body → CTA script that *uses the creator's content as raw material* — keeping their facts, claims, and intent — but rewrites the wording, structure, and pacing to actual ad-copy quality. It is NOT a verbatim reading of what they typed.

**Why this priority**: this is the entire reason the feature exists. Without P1, the gap that prompted the spec stays unresolved. P1 ships the new mode end-to-end.

**Independent Test**: Submit the same brief twice — once in Verbatim mode, once in Polish mode. The Verbatim render's voiceover MUST match the brief word-for-word. The Polish render's voiceover MUST be a structurally different, hook → body → CTA-shaped script that retains the brief's key facts. A human reviewer can tell which is which in 9/10 trials.

**Acceptance Scenarios**:

1. **Given** the script editor in Step 3 with a creator's brief in it, **When** the creator picks Polish + submits, **Then** the rendered voiceover is a 20-second-target marketing script that opens with a hook, develops one body claim from the brief, and closes with a CTA — not a verbatim read.
2. **Given** the same submission in Verbatim mode, **When** the render completes, **Then** the voiceover reads the exact text the creator typed, matching today's behavior bit-for-bit (zero regression).
3. **Given** the same submission in Auto mode (script empty), **When** the render completes, **Then** the voiceover is generated from `video_subject` alone, ignoring the script field — matching today's behavior bit-for-bit (zero regression).
4. **Given** Polish mode is selected but the script editor is empty, **When** the creator clicks submit, **Then** the wizard prevents submission with a typed inline error: "Polish mode needs a brief — type some bullet points or a rough description, then try again."

---

### User Story 2 — Mode selector is clear, discoverable, and remembers state (Priority: P2)

The mode selector in Step 3 makes all three modes visible at once with a short description of each. Picking a mode shows context-appropriate help text under the textarea. The selected mode persists across navigation back-and-forth between wizard steps within the same session.

**Why this priority**: P1 ships the capability; P2 makes it usable. Without P2, the modes exist but creators stumble into the wrong one. Lower than P1 because a buried mode selector is still better than no Polish mode.

**Independent Test**: Open the wizard at Step 3. All three modes are visible at a glance with one-line descriptions. Pick Polish, navigate back to Step 1, return to Step 3 — Polish is still selected. Picking a different mode updates the help text under the textarea immediately.

**Acceptance Scenarios**:

1. **Given** the wizard's Step 3 first opens, **When** the creator looks at the script editor, **Then** the three modes (Auto / Verbatim / Polish) are visible at once, each with a one-line description, and the default is Auto.
2. **Given** the creator picks Polish, **When** the help text below the textarea updates, **Then** it says something like "Type a rough brief — the AI will rewrite it as a 20-second hook → body → CTA script."
3. **Given** the creator picks Verbatim, **When** the help text updates, **Then** it says something like "Your text will be read verbatim as the voiceover."
4. **Given** the creator picks Auto, **When** the help text updates, **Then** it says something like "Leave empty — the AI will write a script from your subject."
5. **Given** the creator picked Polish + typed text + navigated to Step 2 + returned to Step 3, **When** the script editor renders, **Then** Polish mode + the typed text are still in place.

---

### User Story 3 — Existing API consumers + legacy flows behave identically (Priority: P3)

API consumers calling the existing `/api/v1/videos` endpoint without the new mode field MUST see byte-equivalent behavior to today. Empty script → AI writes one. Non-empty script → used verbatim. The wizard's default-mode-on-first-paint MUST also produce byte-equivalent output to today's wizard for an unchanged creator workflow.

**Why this priority**: protects every existing integration + every existing creator's muscle memory. Lower priority than P1/P2 because no end user of the new feature exercises this path explicitly — but a regression here breaks every prior workflow silently. P3 is a hard constraint, not a low-value scope item.

**Independent Test**: Submit a render request via direct curl to `/api/v1/videos` matching today's body shape exactly (no `script_mode` field). Audio output of the rendered MP4 MUST be byte-equivalent to a render submitted before this feature shipped.

**Acceptance Scenarios**:

1. **Given** a render request that omits `script_mode` and provides empty `video_script`, **When** the render completes, **Then** the voiceover is identical to today's "auto" path output (zero regression).
2. **Given** a render request that omits `script_mode` and provides non-empty `video_script`, **When** the render completes, **Then** the voiceover reads the script verbatim — identical to today's verbatim path (zero regression).

---

### Edge Cases

- **Polish mode + empty script**: blocked at the wizard with an inline error (US1 acceptance #4). Backend defensively returns a typed `polish_brief_required` error if the wizard is bypassed.
- **Polish mode + extremely long brief** (more than ~3000 characters): wizard warns "your brief is long — the AI may compress it heavily" but does not block submission.
- **Polish mode + a brief that's already a polished script**: the LLM still runs the polish pass; output may be lightly tweaked. Acceptable trade-off (creators get expected behavior; rare edge case).
- **Polish mode + non-English brief**: the polish prompt instructs the LLM to preserve the brief's original language. Output stays in the brief's language (Spanish brief → Spanish voiceover). Same as today's auto path (which already speaks `video_language`).
- **LLM polish call fails** (rate limit, token quota exceeded, timeout): renders MUST fail closed with a typed error — `polish_failed` — surfaced in the wizard. NEVER silently fall back to using the brief verbatim (that re-introduces the original problem this feature is meant to fix).
- **Polish mode + script field contains only whitespace**: treated as empty per FR-006; wizard shows the same "needs a brief" error as fully empty.
- **Switching modes mid-edit**: changing modes does NOT clear the textarea. Auto-mode hides the textarea (or shows it disabled with a "switch to Verbatim or Polish to enable" hint).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard's Step 3 MUST expose three script modes: **Auto** (default), **Verbatim**, **Polish**. The selector MUST be visible at first paint with all three options + a one-line description per option.
- **FR-002**: When the creator picks **Auto**, the wizard MUST send `video_script=""` and `script_mode="auto"` to MPT (or omit `script_mode` for legacy-compat). Backend behavior: ignore `video_script` entirely; LLM writes from `video_subject`. Identical to today's auto path.
- **FR-003**: When the creator picks **Verbatim**, the wizard MUST send the typed text as `video_script` + `script_mode="verbatim"`. Backend behavior: use `video_script` as the voiceover word-for-word. Identical to today's behavior when script is non-empty.
- **FR-004**: When the creator picks **Polish**, the wizard MUST send the typed text as `video_script` + `script_mode="polish"`. Backend behavior: pass `video_script` as a "brief" parameter to a new LLM polish function; use the LLM's output as the voiceover. The original brief is NOT spoken.
- **FR-005**: A new LLM function (analogous to `generate_marketing_script`) MUST take `(brief: str, video_subject: str, duration_seconds: int, language: str)` and return a polished hook → body → CTA script. The prompt MUST instruct the LLM to: prioritize the brief as creative direction; use `video_subject` (when non-empty — typically the URL-scraped enriched subject from spec 012) as factual product context but never let it override the brief's intent; preserve facts/claims from BOTH inputs; preserve the brief's language; structure as hook (provocative open) → body (one benefit + one proof point) → CTA (single clear action); land within the target word budget for the duration.
- **FR-006**: When `script_mode="polish"` AND `video_script` is empty/whitespace, the backend MUST refuse with a typed `polish_brief_required` error. The wizard MUST also block submission with an inline error matching this contract.
- **FR-007**: When the LLM polish call fails (any reason), the render MUST fail closed with a typed `polish_failed` error. The wizard MUST surface this error and offer "Try Verbatim instead" as a one-click fallback (which preserves the typed text but switches the mode). The render MUST NOT silently fall back to using the brief verbatim.
- **FR-008**: API requests omitting `script_mode` entirely MUST be treated EXACTLY as today's behavior: empty `video_script` → auto path (LLM from subject); non-empty `video_script` → verbatim path. This is the legacy-compat contract — required by FR-010 + SC-005.
- **FR-009**: The new `script_mode` field MUST be added to the existing `VideoParams` Pydantic model as `Optional[Literal["auto", "verbatim", "polish"]] = None`. `None` triggers the legacy-compat behavior in FR-008.
- **FR-009a**: A new optional `script_brief: Optional[str] = None` field MUST be added to `VideoParams`. When `script_mode == "polish"`, the wizard sends the creator's typed text in BOTH `video_script` (which the engine overwrites with the polished output) AND `script_brief` (which is preserved as-is for provenance). When `script_mode != "polish"`, the field MUST be `None` (or omitted).
- **FR-010**: Renders that today produce clean output for any of the three current behaviors (auto with empty script, verbatim with non-empty script, missing field → legacy default) MUST be byte-equivalent in their voiceover content AFTER this feature ships, when the request is unchanged.
- **FR-011**: The wizard's mode + typed text MUST persist across forward/backward navigation within the same session. Refreshing the page MAY reset to defaults (browser state policy is acceptable).
- **FR-012**: The default mode at wizard first-paint MUST be **Auto**. Existing creators who never touch the mode selector MUST experience zero behavioral change vs today.

### Key Entities

- **Script Mode** (new, on `VideoParams`): `Optional[Literal["auto", "verbatim", "polish"]]`. Discriminates the backend's handling of the `video_script` field. `None` falls through to legacy behavior (FR-008).
- **Script Brief**: the contents of `video_script` when `script_mode="polish"`. Free-text input from the creator; ≤ ~3000 characters typical; passed verbatim to the polish LLM function as `brief`. NOT used as voiceover output.
- **Polished Script**: the LLM's output from the polish function. Structured hook → body → CTA. Used as the voiceover for the render. Stored in `task.json`'s `params.video_script` field (same field today's verbatim/auto modes use). Sized to fit `duration_seconds` (default 20 s, until spec 002 lands and exposes per-render duration control).
- **Preserved Brief**: the creator's original typed text. Stored in `task.json`'s new `params.script_brief` field when `script_mode == "polish"`. Never spoken. Enables provenance, debugging, and future regenerate-from-same-brief workflows. Absent (or `None`) for `auto` and `verbatim` modes.
- **Polish Failure Result**: a typed error returned by the backend when the LLM polish call fails. Surfaced in the wizard's progress UI as `polish_failed` + a "Try Verbatim instead" fallback button.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A creator submitting a 50-word brief in Polish mode receives a rendered MP4 whose voiceover differs structurally from the brief — measured as ≥ 50% of the brief's words rewritten or repositioned, with a recognizable hook → body → CTA structure (verifiable by reading the rendered script + comparing).
- **SC-002**: The Verbatim mode produces voiceover word-for-word identical to the input brief in 100% of cases (verified by string comparison of input vs `script.json`'s recorded `script` field, accounting for whitespace normalization).
- **SC-003**: API requests that omit `script_mode` MUST produce identical pipeline output to today's behavior in 100% of test cases (verified by matched-pair render comparison: same `video_subject` + same `video_script`, with vs without the new feature deployed).
- **SC-004**: A creator can switch between Auto / Verbatim / Polish modes in the wizard in under 3 seconds per switch (selector visible, no nested menus). Verified by user observation.
- **SC-005**: All three modes' help text + behavior is internally consistent — Auto hides the textarea, Verbatim/Polish show it with mode-appropriate hints. Manual UX review.
- **SC-006**: When Polish mode is selected with an empty brief, the wizard MUST surface a typed inline error within 100 ms of submit-click. Backend defensively returns the same error if the wizard validation is bypassed.
- **SC-007**: When the LLM polish call fails (synthetic injection of an OpenAI 429 / quota / timeout), the render MUST fail closed with `polish_failed` — verified by inspecting `script.json`'s state field. Zero silent fallbacks (matches the discipline in spec 009 / 010 / 012).

## Assumptions

- **The LLM polish prompt is a small additive function in `app/services/llm.py`**, alongside `generate_marketing_script`. Same model (gpt-4o-mini), same retry policy, same `_generate_response` plumbing — adding ~30 lines of new function code with a hand-tuned prompt template.
- **The polish target duration is fixed at 20 seconds at v1.** When spec 002 (duration / variations / preview-gate) ships, polish mode inherits the same per-render duration control as auto mode. v1 stays at the `generate_marketing_script` default.
- **The polish prompt preserves the brief's language.** No translation. If the creator pastes a Spanish brief, the output is Spanish — same as today's auto path which already obeys `video_language`.
- **Polish mode is bounded to Mode 2 at v1.** Modes 1 / 3 / 4 / 5 do not yet have wizards; when they do, each ships its own polish prompt tuned to that mode's content shape (educational, long-form, UGC, faceless). Spec 013 only delivers Mode 2's polish path.
- **Mode selector state is wizard-local at v1.** Not persisted to localStorage or per-tenant preferences. When debt #2 repays in Step 2, per-tenant defaults can be added without schema change.
- **The wizard's Step 1 enriched-subject path (spec 012) and Step 3 polish mode (this spec) compose cleanly.** A creator can paste a URL in Step 1 (scraped → enriched subject), then write a brief in Step 3 + pick Polish (LLM polishes the brief, NOT the enriched subject). The two features address different layers of the input pipeline and don't conflict.
- **Polish mode failure recovery is creator-driven.** When `polish_failed` fires, the wizard offers "Try Verbatim instead" — preserving the typed text but switching modes — rather than auto-retrying. Auto-retry would mask transient LLM hiccups but obscure persistent issues.

## Dependencies

- Touches **fork-surface files**: `app/models/schema.py` (one new optional field on `VideoParams`), `app/services/llm.py` (new `polish_script` function), `app/services/task.py` (one new dispatch line — continuation of debt #5). Layer 1 wizard + `/api/generate` proxy added incrementally.
- **Spec 002** (duration/variations) is independent — this spec ships at the existing 20s target and inherits new duration control automatically when spec 002 lands.
- **Spec 012** (URL scraping) is independent — both can ship in any order; the enriched-subject path lives in Step 1, polish mode lives in Step 3.

## Constitutional Impact

| Principle | Impact | Mitigation |
|---|---|---|
| **I. Layer 3 Scope** | None — this is render-engine LLM work, exactly Layer 3's job. | n/a |
| **II. Surgical Fork Discipline** | Touches **fork-surface** `app/models/schema.py` (new optional field) and `app/services/llm.py` (new function). Adds a 3rd one-line touch to `app/services/task.py` — continues debt #5. | task.py debt #5 already tracks two prior touch lines; one more on the same dispatch site is incremental. Repays cleanly when Step 3's mode registry lands. |
| **III. Multi-Tenant Context Propagation** | None — feature has no per-render auth surface. | n/a |
| **IV. External Asset Acceptance** | None — uses existing OpenAI integration that's already in `llm.py`; no new external API. | n/a |
| **V. Mode-Aware Rendering Contract** | Polish prompt is hardcoded inline in `llm.py` for Mode 2. Continues debt #4 (Mode 2 prompts inline rather than in `app/services/modes/`). When debt #4 repays in Step 3, the polish prompt moves into the mode registry alongside `generate_marketing_script`. | Continuation of debt #4; no new debt. |

**Net constitutional impact**: zero new debts. Debts #4 + #5 each gain one more burndown task — both repay cleanly when Step 3's mode registry lands.

## Cross-references

- [Spec 010 — Music Track Control](../010-music-control/spec.md) — sibling Layer-3 + Layer-1 feature; same shape (schema field + Pydantic-typed mode + wizard panel). Already shipped 2026-05-02.
- [Spec 012 — URL Scraping for Step 1 Input](../012-url-scraping/spec.md) — sibling honest-UX feature that resolved the Step 1 capability gap; this spec resolves the analogous Step 3 gap. Already shipped 2026-05-02.
- [Spec 002 — Video Duration / Variations / Preview Gate](../002-video-duration-variations/spec.md) — independent; ships duration control. Polish mode inherits it cleanly when 002 lands.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — debts #4 + #5 each get one more burndown task; no new debts.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle II (fork-surface) + Principle V (mode-aware rendering) governance applies, with the same patterns specs 010 + 012 + 009 already follow.
- [`app/services/llm.py:603-628`](../../app/services/llm.py#L603-L628) — `generate_marketing_script` function the new `polish_script` function will live next to.
