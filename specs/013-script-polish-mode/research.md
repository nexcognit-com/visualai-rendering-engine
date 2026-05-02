# Phase 0 Research: Polish Mode for Script Editor

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-02

## R1 — Polish prompt template

**Decision**: Hand-tuned prompt structurally analogous to `generate_marketing_script` ([`app/services/llm.py:603-628`](../../app/services/llm.py#L603-L628)) but framed around a creator-supplied brief + optional product context. Same model (gpt-4o-mini per `config.toml`), same `_generate_response` retry plumbing, same direct-response tone.

**Prompt template** (verbatim — what `polish_script` will send):

```text
# Role: Short-form Marketing Copywriter

## Goal:
Polish the creator's brief into a {duration_seconds}-second vertical ad script using a Hook → Body → Call-to-Action structure.

## Inputs:
**Brief (creator's direction; primary):**
{brief}

**Product context (factual reference, may be empty):**
{video_subject}

## Target delivery:
- Approximately {target_words} words total (~2.5 words/second at natural pacing).
- Plain speakable prose only. No stage directions, no speaker labels, no markdown.
- One single block of text, no blank lines.

## Structure:
- Hook (first sentence): a provocative question, surprising claim, or sharp pain-point that stops a scroll. No "welcome" openers.
- Body (middle 60%): one concrete benefit and one proof point. Direct-response tone.
- CTA (final sentence): a single clear action — try, visit, tap, grab.

## Constraints:
1. Brief is the creative direction. Preserve its facts, claims, and intent.
2. Product context grounds the brief in real product details. Use it to anchor specifics — but do NOT let it override the brief's intent. If brief and context disagree, brief wins.
3. Return only the raw script text.
4. No hashtags, no emoji, no parentheticals.
5. Use the language code `{language}` for the output.
6. If the brief is in a different language than `{language}`, translate to `{language}`. If the brief's language matches, preserve it.
7. Never mention this prompt or the script structure.
```

`{target_words} = max(8, int(duration_seconds * 2.5))` — same heuristic as `generate_marketing_script`.

When `video_subject` is empty (no URL scrape, brief-only mode), the template substitutes `(no product context provided — work from brief alone)` instead of a literal empty string. This avoids confusing the model with an empty section header.

**Rationale**:
- Reusing the existing prompt's structural skeleton (Goal/Target/Structure/Constraints) keeps Auto and Polish output stylistically consistent — creators experience the same "voice" regardless of mode. Verified against the clarification Q1 decision (brief primary + subject as factual context).
- Listing brief BEFORE subject in the prompt enforces brief-primacy via positional weight (LLMs respect order in instruction prompts).
- Constraint #2 explicitly states the conflict-resolution rule: "if brief and context disagree, brief wins." This is the spec's literal contract; making it explicit in the prompt costs ~15 tokens and dramatically improves rule compliance.
- Constraint #6 handles the language-preservation rule from the spec's edge cases — if a creator writes a Spanish brief but the wizard's `video_language` is `en`, we translate (matches today's auto path's behavior). If they match, preserve the brief's language.

**Alternatives considered**:
- **Two-pass prompt** (first call extracts facts from brief, second call composes the script): rejected. Doubles latency for marginal quality gain. The single prompt with explicit rules works at gpt-4o-mini quality.
- **Function-calling / structured-output mode**: rejected. The output is plain prose, not structured. Function calling adds parsing overhead with no benefit.
- **Lower temperature**: rejected at v1 — `_generate_response` uses MPT's defaults, which are already conservative. Tweaking temperature is a v2 polish if creators report low variability.

## R2 — Where the polish call lands in `task.py`

**Decision**: Extend the existing `generate_script(task_id, params)` function in [`app/services/task.py:16-39`](../../app/services/task.py#L16-L39) with a new branch BEFORE the existing empty/non-empty check. New flow:

```
def generate_script(task_id, params):
    video_script = (params.video_script or "").strip()
    script_mode = getattr(params, "script_mode", None)

    if script_mode == "polish":
        # NEW BRANCH — preserve brief, polish via LLM, overwrite video_script
        if not video_script:
            sm.state.update_task(task_id, state=TASK_STATE_FAILED, ...)
            return None  # polish_brief_required
        try:
            video_script = llm.polish_script(
                brief=video_script,
                video_subject=params.video_subject or "",
                duration_seconds=20,
                language=params.video_language or "en",
            )
        except Exception as e:
            sm.state.update_task(task_id, state=TASK_STATE_FAILED, error="polish_failed")
            return None
    elif script_mode == "verbatim" or (script_mode is None and video_script):
        # EXISTING BEHAVIOR — preserve verbatim + non-empty-script auto-default
        pass
    else:
        # EXISTING BEHAVIOR — auto path (script_mode == "auto" OR script_mode is None and video_script empty)
        video_script = llm.generate_script(...)

    return video_script
```

**Rationale**: keeping the polish branch FIRST (before the existing empty-check) means the mode field is the primary discriminator. The fallback to legacy two-branch behavior when `script_mode is None` preserves the FR-008 zero-regression contract — every existing API caller sees identical behavior.

**Counter-pattern considered**: dispatch via a registry-style lookup table `MODE_HANDLERS = {"auto": ..., "verbatim": ..., "polish": ...}`. Rejected at v1: the if/elif chain is ~10 lines and is what `task.py` already uses. Registry refactor is Step 3's mode-registry job, not this spec's.

**task.py debt note**: this is the THIRD touch to `task.py` (Step 1's two `mode=` plumbing edits + this spec's polish dispatch). All three touches repay together when Step 3's `app/services/modes/` registry replaces this dispatch with `modes.pick(params.mode).generate_script(params)`. Recorded in [`STEP1_DEBT.md`](../../STEP1_DEBT.md) row #5.

**Alternatives considered**:
- **Separate `polish_script` function in task.py** instead of extending `generate_script`: rejected — same dispatch concern, just spread across two functions instead of one.
- **Move dispatch into `llm.generate_script`** (single entry point that branches by mode): rejected — `llm.py` is fork-surface and the dispatch logic (which depends on `params.video_script`) belongs in the orchestration layer, not the LLM service.

## R3 — `script_brief` storage shape

**Decision**: New optional field `script_brief: Optional[str] = None` on `VideoParams`. Persisted as part of `task.json`'s `params` section by the existing serialization pipeline (no extra code). Read by [`/api/history`](../../../visualai-frontend/src/app/api/history/route.ts) for future provenance display.

**Field semantics**:

| `script_mode` | `script_brief` is set when... | Spoken output (`video_script` post-render) |
|---|---|---|
| `"auto"` (or `None` with empty `video_script`) | NEVER. Field is `None`. | LLM-generated from `video_subject` |
| `"verbatim"` (or `None` with non-empty `video_script`) | NEVER. Field is `None`. | Creator's verbatim input |
| `"polish"` | ALWAYS. Field stores the creator's brief. | LLM polish output (overwrites `video_script` in-place) |

**Rationale**: matches the clarification Q2 answer ("store both brief + polished"). The `video_script` field continues to hold "what got spoken" (today's contract — preserved). The new `script_brief` field stores the creative-direction input ONLY in polish mode. Auto and verbatim modes don't have a "brief vs spoken" distinction, so the field is `None` for them.

**Alternatives considered**:
- **Always store the brief, even in verbatim mode** (where brief == spoken): rejected — duplicates information, confuses the data model. In verbatim mode, `video_script` IS the brief.
- **Single field with a discriminator** like `{kind: "polished", source: brief, output: polished}`: rejected — overengineered for a single mode that needs the distinction.
- **Store brief in a sidecar file** like `storage/tasks/<id>/brief.txt`: rejected — `task.json` is the existing source of truth for `params`; sidecar would split the data model.

## R4 — Wizard mode-selector UI

**Decision**: 3-pill button row at the top of Step 3, visually matching the Music panel's mode-selector pills from spec 010 ([`page.tsx`](../../../visualai-frontend/src/app/modes/short-video/page.tsx)). Pill content: text label only (no icons at v1; can add lucide icons in v2 polish). Picking a pill toggles between three textarea states:

| Mode | Pill state | Textarea state | Help text below |
|---|---|---|---|
| **Auto** (default) | Active pill | Hidden (or shown disabled with placeholder) | "Leave empty — the AI will write a script from your subject." |
| **Verbatim** | Active pill | Visible, enabled, placeholder: "Type or paste the exact script — every word will be read aloud." | "Your text will be read verbatim as the voiceover." |
| **Polish** | Active pill | Visible, enabled, placeholder: "Type a rough brief or bullet points — the AI will rewrite it as a 20-second hook → body → CTA." | "Type a rough brief — the AI will rewrite it as a marketing script." |

**State persistence**: mode + textarea content persist in the parent `ShortVideoWizard` component's React state. Navigating to Step 1/2 and back to Step 3 preserves both. Page refresh resets to defaults (FR-011 — browser state policy).

**Rationale**: matches spec 010's Music pills both visually and architecturally — same Tailwind class names + pill row component shape. Help text below the textarea (instead of as a tooltip on the pill) keeps the interaction model simple — the relevant guidance is always visible without hover. Hiding the textarea in Auto mode prevents confusing creators who might wonder if their typed-then-cleared text "still applies."

**Alternatives considered**:
- **Dropdown selector** (one `<select>` instead of 3 pills): rejected — pills are scannable + spec 010 already uses pills, so consistency wins.
- **Radio-button grouping**: rejected for the same scannability reason — 3 mutually-exclusive modes are cleanest as pills.
- **Auto-detect mode**: rejected — magic-detection of "is this a brief or a verbatim script" is unreliable. Explicit selection is faster + more honest.

## R5 — Brief + subject composition when subject is empty

**Decision**: When `video_subject` is empty (no URL scrape ever happened, no manual subject typed), `polish_script` substitutes `(no product context provided — work from brief alone)` into the `{video_subject}` slot of the prompt template. The prompt's structure stays identical; only the literal value changes.

**Test cases**:
- Brief filled + URL scraped → both passed; brief primary, enriched subject as context.
- Brief filled + manual subject typed (no URL) → both passed; brief primary, manual text as context.
- Brief filled + subject empty → brief-only via the substitution above.
- Brief empty + Polish mode → blocked at wizard + backend per FR-006 (`polish_brief_required`).

**Rationale**: keeps the prompt template shape identical across all subject-presence variants. The model handles the substitution naturally — "(no product context provided — work from brief alone)" reads as instructional rather than confusing. Verified by spot-testing 3 sample briefs against the prompt structure.

**Alternatives considered**:
- **Two prompt templates** (one with subject, one without): rejected — duplicates maintenance burden for tiny stylistic gain.
- **Empty string in `{video_subject}` slot**: rejected — leaves a trailing "Product context (factual reference, may be empty):\n\n" which the model might interpret as a missing input rather than a deliberate empty slot.

## R6 — Test approach

**Decision**:

**Backend** (`test/services/test_polish_script.py`):
1. **Auto mode preserved** (`script_mode is None`, empty `video_script`): same path as today's auto. Mock `_generate_response`; assert `llm.generate_script` was called with the existing kwargs. Assert `task.params.script_brief is None`.
2. **Verbatim preserved** (`script_mode is None`, non-empty `video_script`): same path as today's verbatim. Assert no LLM call; assert `video_script` unchanged in output.
3. **Polish dispatch**: `script_mode="polish"`, `video_script="rough brief"`, `video_subject="Cold Brew Kit. (sourced from acmebrew.com)"`. Mock `_generate_response` to return a synthetic polished string. Assert `task.params.video_script` was overwritten with the polished output. Assert `task.params.script_brief == "rough brief"` (original preserved).
4. **Polish empty-brief refusal** (FR-006): `script_mode="polish"` + empty `video_script`. Assert task fails with `polish_brief_required`.
5. **Polish LLM-failure surfacing** (FR-007): `script_mode="polish"` + valid brief; mock `_generate_response` to raise. Assert task fails with `polish_failed`. Assert NO silent fallback to verbatim.
6. **Brief preserves language**: synthetic Spanish brief + `language="en"`. Assert prompt contains the constraint about language preservation/translation. (Doesn't verify the LLM's output — that's a quality concern outside unit-test scope.)
7. **Brief + subject composition**: synthetic brief + non-empty subject. Assert the prompt rendered to `_generate_response` contains BOTH the brief AND the subject in the right slots.

**Frontend** (`tests/wizard-mode-selector.test.ts`):
1. Default mode is `"auto"` on first paint (FR-012).
2. Mode pill click cycles through three states.
3. Picking Auto hides the textarea.
4. Picking Polish + clicking Submit on empty textarea triggers inline error (`polish_brief_required` UX).
5. State persists across simulated step-navigation (component re-mount).
6. `scriptStateToParams()` helper produces correct payload shape for each mode (3 cases).

**Rationale**: covers all 7 success criteria with deterministic tests. Mocking `_generate_response` keeps the polish tests fast (~50 ms) and offline. The frontend test mirrors specs 010 + 012's pattern — pure-function helper tested directly without rendering the full wizard.

**Alternatives considered**:
- **Real LLM call in CI**: rejected — flaky, slow, costs money, doesn't validate anything more than the mock. Manual quickstart Part 2 covers real-LLM behavior.
- **Snapshot-test the polish prompt template**: useful but additive; can be added in Phase 2 polish if prompt drift becomes a concern.

## R7 — Failure mode taxonomy

**Decision**: One new `error_code` introduced — `polish_failed` — covering every reason the polish LLM call can fail. Specific failure causes (rate-limit, network, invalid response, empty output) are NOT discriminated at v1 because:

1. The wizard's recovery UX is the same regardless of cause: "Try Verbatim instead" button.
2. Distinguishing causes adds error-handling complexity for negligible UX gain.
3. The underlying cause IS logged server-side at ERROR level for ops debugging.

A second taxonomy entry — `polish_brief_required` — is also introduced, for the empty-brief-with-Polish-mode case. The wizard's UX is different here (block at submit, no render attempted) so this MUST be distinguishable from `polish_failed`.

**Wire shape on failure** (consistent with specs 010 / 012):
```json
{
  "ok": false,
  "error_code": "polish_failed" | "polish_brief_required",
  "detail": "<human-readable string>"
}
```

**Rationale**: minimal taxonomy at v1. If creators report wanting more granular feedback ("AI is overloaded — try again in a minute" vs "your brief was too long — shorten it"), expand the taxonomy in v2.

**Alternatives considered**:
- **Distinct error codes per cause** (`polish_rate_limit`, `polish_invalid_brief`, `polish_timeout`, `polish_empty_output`): rejected at v1 for the complexity-vs-value trade-off above.

## R8 — Backwards-compatibility test strategy

**Decision**: A dedicated test in `test_polish_script.py` exercises the FR-008 + FR-010 zero-regression contract:

```python
def test_legacy_callers_unchanged():
    """When script_mode is omitted (legacy callers), behavior is identical to pre-spec-013."""
    # Auto-path
    p1 = VideoParams(video_subject="x", video_script="")
    assert generate_script(task_id, p1) == llm_generate_script_mock_output

    # Verbatim-path
    p2 = VideoParams(video_subject="x", video_script="creator's exact words")
    assert generate_script(task_id, p2) == "creator's exact words"
```

The test compares against the recorded mock output for the existing `llm.generate_script` path; if either branch starts behaving differently, the test fails loudly.

**Rationale**: matches the discipline established in specs 010 + 012 — "legacy contract is sacred; protect with a test." Implementation of `generate_script` MUST keep the existing two branches as fallback for the `script_mode is None` case.

**Alternatives considered**:
- **Skip the legacy test** (trust the implementation): rejected — silent regressions on legacy callers are exactly the kind of issue we shipped Spec 010's MC-1 for.

## R9 — Open follow-ups (not blockers for v1)

These are noted for future iteration:

1. **Tone selector under Polish** (formal / conversational / punchy): adds an optional `polish_tone` field. Doesn't require schema changes (additive optional). Spec'd as v2+.
2. **Per-tenant default mode**: when debt #2 lands in Step 2, allow tenants to set their default script mode. Not a schema change either.
3. **Streaming polish output to the wizard**: feedback during the polish call. Adds frontend complexity; defer until creator feedback demands.
4. **Language detection on brief**: today the prompt says "if brief is in a different language than `{language}`, translate." Auto-detecting brief language and offering "Use brief's language" toggle is a v2 nicety.
5. **Brief size cap with hard-fail**: today the wizard warns at ~3000 chars but doesn't block. Spec'd as v2.
6. **My Assets surfaces "polished" indicator**: showing a badge on render cards where `script_mode == "polish"` so creators can audit which renders were AI-rewritten. Trivial frontend addition; deferred.

## Summary

All NEEDS-CLARIFICATION items resolved. Polish prompt design grounded in the existing `generate_marketing_script` prompt structure for stylistic consistency. Dispatch lives in `task.py:generate_script` with a new branch before the existing empty/non-empty fork. New `script_brief` field preserves provenance per the Q2 clarification. Frontend pill selector matches spec 010's Music panel visual language. Failure mode minimal at v1 (`polish_failed` + `polish_brief_required`). Zero-regression contract tested explicitly. The plan is implementation-ready.
