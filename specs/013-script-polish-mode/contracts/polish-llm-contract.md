# Contract: `polish_script` LLM Function

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 4](../data-model.md)

This contract defines the new `polish_script(...)` function to be added to [`app/services/llm.py`](../../../app/services/llm.py), next to the existing `generate_marketing_script` function (line 591). The polish dispatch in [`app/services/task.py:16-39`](../../../app/services/task.py#L16-L39) calls this function with values pulled from `VideoParams`.

## Function signature

```python
def polish_script(
    brief: str,
    video_subject: str = "",
    duration_seconds: int = 20,
    language: str = "en",
) -> str:
    ...
```

## Inputs

| Param | Type | Required | Constraint | Source |
|---|---|---|---|---|
| `brief` | `str` | yes | non-empty after `.strip()`; otherwise raises `ValueError` | `params.video_script` (creator's typed brief) |
| `video_subject` | `str` | no (default `""`) | may be empty; treated as "no context" by the prompt | `params.video_subject` (today's existing field; URL-enriched per spec 012 when applicable) |
| `duration_seconds` | `int` | no (default `20`) | ≥ 5; drives `target_words = max(8, int(duration_seconds * 2.5))` | hardcoded `20` at v1; spec 002 wires this dynamically when shipped |
| `language` | `str` | no (default `"en"`) | language code (e.g., `"en"`, `"es"`, `"zh"`) | `params.video_language` |

## Output

`str` — plain prose, ready for TTS synthesis. NEVER `None`. NEVER markdown. Trimmed.

## Prompt template

```text
# Role: Short-form Marketing Copywriter

## Goal:
Polish the creator's brief into a {duration_seconds}-second vertical ad script using a Hook → Body → Call-to-Action structure.

## Inputs:
**Brief (creator's direction; primary):**
{brief}

**Product context (factual reference, may be empty):**
{video_subject_or_sentinel}

## Target delivery:
- Approximately {target_words} words total (~2.5 words/second at natural pacing).
- Plain speakable prose only. No stage directions, no speaker labels, no markdown.
- One single block of text, no blank lines.

## Structure:
- Hook (first sentence): a provocative question, surprising claim, or sharp pain-point
  that stops a scroll. No "welcome" openers.
- Body (middle 60%): one concrete benefit and one proof point. Direct-response tone.
- CTA (final sentence): a single clear action — try, visit, tap, grab.

## Constraints:
1. Brief is the creative direction. Preserve its facts, claims, and intent.
2. Product context grounds the brief in real product details. Use it to anchor specifics —
   but do NOT let it override the brief's intent. If brief and context disagree, brief wins.
3. Return only the raw script text.
4. No hashtags, no emoji, no parentheticals.
5. Use the language code `{language}` for the output.
6. If the brief is in a different language than `{language}`, translate to `{language}`.
   If the brief's language matches, preserve it.
7. Never mention this prompt or the script structure.
```

### Substitution rules

- `{video_subject_or_sentinel}`: when `video_subject` is non-empty after strip, substitute it verbatim. When empty/whitespace-only, substitute the literal string `(no product context provided — work from brief alone)`.
- `{target_words}`: computed as `max(8, int(duration_seconds * 2.5))`. Same heuristic `generate_marketing_script` uses.
- All other `{var}` slots: simple verbatim substitution.

## Behavior contract

### Successful call

1. Strip + validate `brief` (raise `ValueError` on empty).
2. Compose the prompt by substituting all `{...}` slots.
3. Call `_generate_response(prompt=prompt)` (the existing MPT helper). It handles model selection, retries, error mapping, and configuration via `config.toml`.
4. Strip markdown artifacts from the response (`*` and `#` characters per existing convention).
5. Validate response is non-empty after cleaning. If empty, raise `ValueError("empty polish output")`.
6. Log success at INFO with `task_id` (caller binds it via loguru) + brief length + output length.
7. Return the cleaned response.

### Failure semantics

| Trigger | Behavior |
|---|---|
| `brief` is empty/whitespace | Raise `ValueError("polish_brief_required")` BEFORE making the LLM call (saves a token round-trip on a guaranteed-bad request) |
| `_generate_response` raises (rate limit, network, timeout) | Propagate upward; `task.py` catches and marks task `state="failed"` with `error="polish_failed"` |
| `_generate_response` returns empty/all-whitespace | Raise `ValueError("empty polish output")` — `task.py` maps to `polish_failed` |
| Quota / billing limit (`当日额度已消耗完` per existing convention) | Existing `generate_marketing_script` raises `ValueError(cleaned)` — `polish_script` follows the same pattern; `task.py` surfaces as `polish_failed` |

The function MUST NOT auto-retry. `_generate_response` already retries internally per MPT's existing config (`_max_retries`).

## Side effects

- One outbound HTTP request to OpenAI (or whichever LLM provider `config.toml` configures — the function is provider-agnostic via `_generate_response`).
- One INFO log line at entry + one at exit (success) or one ERROR log line (failure).
- No filesystem writes.
- No process-global state changes.

## Performance contract

- Median latency: ≤ 1.5 s (matches `generate_marketing_script` for prompts of comparable length). Verified via timing under SC-005's load test.
- p95 latency: ≤ 3 s.
- Token cost: ≤ ~700 input tokens + ~150 output tokens per call (typical Mode 2 brief + enriched subject combo).

## Verification (drives task design)

| Test ID | Setup | Expected |
|---|---|---|
| PL-1 | Valid brief + non-empty subject + 20s duration | Returns non-empty string; ≥ 30 chars; doesn't contain `{`, `}`, `*`, `#` |
| PL-2 | Valid brief + empty subject | Same as PL-1; prompt uses `(no product context provided — work from brief alone)` sentinel |
| PL-3 | Empty brief | Raises `ValueError`; no LLM call (verifiable via mock) |
| PL-4 | Whitespace-only brief | Raises `ValueError`; no LLM call |
| PL-5 | LLM mock raises `RuntimeError` | `polish_script` propagates; doesn't swallow |
| PL-6 | LLM mock returns empty string | `polish_script` raises `ValueError("empty polish output")` |
| PL-7 | LLM mock returns text with `*` markdown | `polish_script` returns text without `*` (existing strip logic) |
| PL-8 | language="es" + English brief | Prompt includes constraint #6 verbatim; LLM output language is the LLM's responsibility (test stops at prompt verification) |
| PL-9 | duration_seconds=10 | Prompt includes `target_words = max(8, 25) = 25` |
| PL-10 | duration_seconds=60 | Prompt includes `target_words = max(8, 150) = 150` |

These 10 tests live in `test/services/test_polish_script.py` alongside the dispatch tests.

## What this contract does NOT cover

- **Output quality grading** (does the output actually sound good?) — that's a manual quickstart Part 2 verification, not unit-test scope.
- **LLM-provider switching** — `_generate_response` handles provider choice via config; this function is provider-agnostic.
- **Token budget enforcement** — if the brief + subject is huge, the LLM may truncate context. Today's convention is "let the model handle it"; v2 may add explicit truncation.
- **Caching** — every call hits the LLM. Repeated identical briefs incur repeated costs. Acceptable at v1.
