# Contract: Script Mode Wire Shape

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 1 + §Entity 2](../data-model.md)

The wire shape `script_mode` + `script_brief` take inside `/api/v1/videos` requests, plus the dispatch matrix MPT applies in [`app/services/task.py:generate_script()`](../../../app/services/task.py).

This contract is the **single source of truth** for "what does each combination of fields mean." Both the wizard's TypeScript types and `task.py`'s if/elif chain MUST match this matrix.

## Field shape

```jsonc
// Inside POST /api/v1/videos body — VideoParams
{
  "video_subject": "<existing — required-ish>",
  "video_script": "<existing — string, may be empty>",
  "video_language": "<existing — language code>",
  "script_mode": "auto" | "verbatim" | "polish" | null,  // NEW (default null)
  "script_brief": "<string>" | null,                       // NEW (default null)
  // ... all existing fields ...
}
```

## Dispatch matrix

The single authoritative table. Implementation MUST match it row-for-row.

| Row | `script_mode` | `video_script` (after `.strip()`) | Path taken | Source of voiceover (post-render `params.video_script`) | `params.script_brief` after render |
|---|---|---|---|---|---|
| L1 | `null` | empty | Legacy auto | `llm.generate_script(video_subject=..., language=..., paragraph_number=..., mode=...)` | `null` |
| L2 | `null` | non-empty | Legacy verbatim | unchanged input | `null` |
| A1 | `"auto"` | empty (or any value — ignored) | Explicit auto | same as L1 | `null` |
| V1 | `"verbatim"` | non-empty | Explicit verbatim | unchanged input (same as L2) | `null` |
| V2 | `"verbatim"` | empty | **ERROR** (wizard blocks; backend defensively falls through to A1 OR returns 400) | n/a | n/a |
| P1 | `"polish"` | non-empty | Polish | `llm.polish_script(brief=video_script, video_subject=..., duration_seconds=20, language=...)`; result OVERWRITES `video_script` in-place | original brief preserved |
| P2 | `"polish"` | empty | **ERROR** `polish_brief_required` | n/a | n/a |

### Equivalence guarantees

- **L1 ≡ A1**: identical observable output. The wizard sends explicit `"auto"`; legacy callers send `null` + empty `video_script`. Both produce the same auto-path render.
- **L2 ≡ V1**: identical observable output. The wizard sends explicit `"verbatim"`; legacy callers send `null` + non-empty `video_script`. Both produce the same verbatim render.
- **P1 is new**: no equivalent in legacy. Only fires when the wizard explicitly sends `"polish"`.

These equivalences are the FR-008 + FR-010 zero-regression contract enforcement points.

## Wizard payload composition (Layer 1 contract)

The wizard's `scriptStateToParams()` helper produces these exact shapes (from [data-model.md §Entity 3](../data-model.md)):

```ts
// Auto mode
{ script_mode: "auto", video_script: "" }
// Verbatim mode
{ script_mode: "verbatim", video_script: "creator's exact text" }
// Polish mode
{
  script_mode: "polish",
  video_script: "creator's brief (will be overwritten in-place by polish output)",
  script_brief: "creator's brief (preserved)",
}
```

The frontend's `/api/generate` proxy passes these through verbatim to MPT.

## Backend dispatch (Layer 3 contract)

[`app/services/task.py:generate_script()`](../../../app/services/task.py#L16-L39) MUST implement the dispatch matrix as:

```python
def generate_script(task_id, params):
    video_script = (params.video_script or "").strip()
    script_mode = getattr(params, "script_mode", None)

    # Polish mode
    if script_mode == "polish":
        if not video_script:
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                error="polish_brief_required",
            )
            return None
        try:
            video_script = llm.polish_script(
                brief=video_script,
                video_subject=params.video_subject or "",
                duration_seconds=20,
                language=params.video_language or "en",
            )
        except Exception as exc:
            logger.error(f"polish_script failed: {exc}")
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                error="polish_failed",
            )
            return None
        if not video_script:
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                error="polish_failed",
            )
            return None

    # Verbatim mode (or legacy non-empty)
    elif script_mode == "verbatim" or (script_mode is None and video_script):
        # No-op — video_script already set
        pass

    # Auto mode (explicit OR legacy empty)
    else:
        video_script = llm.generate_script(
            video_subject=params.video_subject,
            language=params.video_language,
            paragraph_number=params.paragraph_number,
            mode=getattr(params, "mode", "faceless"),
        )

    if not video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video script.")
        return None

    return video_script
```

(Pseudocode — implementation should integrate with the existing helper imports and logging conventions.)

## Error wire shape

When the dispatch fails, the task moves to state `"failed"` and `script.json`'s `error` field carries the typed code:

| Trigger | `task.json.error` | Wizard UX |
|---|---|---|
| `script_mode == "polish"` + empty `video_script` | `"polish_brief_required"` | "Polish mode needs a brief — type some bullet points or a rough description, then try again." |
| `polish_script` raises any exception | `"polish_failed"` | "We couldn't polish that brief — try again, or switch to Verbatim to use your text as-is." (with a "Try Verbatim instead" button) |

The wizard polls `/api/status/<task_id>` (existing flow) and surfaces these error codes.

## Verification (drives task design)

| Test ID | Setup | Expected |
|---|---|---|
| WS-1 | `{script_mode: null, video_script: ""}` | Legacy auto path (L1) |
| WS-2 | `{script_mode: null, video_script: "x"}` | Legacy verbatim (L2) |
| WS-3 | `{script_mode: "auto", video_script: ""}` | Explicit auto (A1) — equivalent to WS-1 |
| WS-4 | `{script_mode: "auto", video_script: "ignored"}` | Auto path; `video_script` ignored (A1) |
| WS-5 | `{script_mode: "verbatim", video_script: "x"}` | Verbatim (V1) — equivalent to WS-2 |
| WS-6 | `{script_mode: "verbatim", video_script: ""}` | Backend defensive fall-through to A1 (V2 — wizard prevents this case) |
| WS-7 | `{script_mode: "polish", video_script: "rough"}` | Polish (P1); LLM mock returns `"polished"`; `params.video_script == "polished"`; `params.script_brief == "rough"` |
| WS-8 | `{script_mode: "polish", video_script: ""}` | `polish_brief_required` error (P2) |
| WS-9 | `{script_mode: "polish", video_script: "rough"}`; LLM mock raises | `polish_failed` error |
| WS-10 | `{script_mode: "polish"}` AND `{video_subject: "Cold Brew Kit. (sourced from acmebrew.com)"}` | Polish prompt rendered to LLM contains BOTH the brief AND the enriched subject (Q1 clarification verification) |

These 10 tests are scheduled in `tasks.md` for Phase 2.

## What this contract does NOT cover

- **Wizard UI shape** — see [`wizard-mode-selector-contract.md`](./wizard-mode-selector-contract.md).
- **Polish prompt details** — see [`polish-llm-contract.md`](./polish-llm-contract.md).
- **Status polling shape** — unchanged; existing `/api/status/<task_id>` returns `task.json` verbatim.
