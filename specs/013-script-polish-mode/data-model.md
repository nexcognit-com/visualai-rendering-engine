# Phase 1 Data Model: Polish Mode for Script Editor

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This feature introduces TWO new fields on the existing `VideoParams` Pydantic model and ONE new TypeScript wizard-state shape on Layer 1. No new entities, no new tables, no new DB schema. Layer 3's `task.json` serialization picks up both new fields automatically (existing pipeline serializes the full `VideoParams`).

---

## Entity 1 — `VideoParams.script_mode` (new field)

**File**: [`app/models/schema.py`](../../app/models/schema.py)
**Cardinality**: one optional value per render request

### Schema (Pydantic v2)

```python
from typing import Optional, Literal

ScriptMode = Literal["auto", "verbatim", "polish"]

class VideoParams(BaseModel):
    # ... existing fields ...
    script_mode: Optional[ScriptMode] = None
    # ... existing fields ...
```

### Field-level contract

| Aspect | Value |
|---|---|
| Type | `Optional[Literal["auto", "verbatim", "polish"]]` |
| Default | `None` |
| Required | No |

### Validation invariants

1. `script_mode` is one of `"auto"`, `"verbatim"`, `"polish"`, OR `None`. No other values accepted (Pydantic Literal enforces this — emits 422 on bad input).
2. `script_mode == "polish"` REQUIRES `video_script` to be a non-empty string after `.strip()`. Backend returns `polish_brief_required` error if violated.
3. `script_mode == "auto"` triggers explicit auto-path even when `video_script` is non-empty. (Differs from `script_mode = None` + non-empty `video_script` — that's legacy verbatim.)
4. `script_mode == "verbatim"` is functionally equivalent to today's "non-empty video_script + None mode" — but it's an explicit signal. Preferred over leaving it `None` once the wizard ships.

### Dispatch matrix (FR-002 + FR-003 + FR-004 + FR-008)

| `script_mode` | `video_script` | Behavior | Source of voiceover |
|---|---|---|---|
| `None` (legacy) | empty/whitespace | Auto path | `llm.generate_script(video_subject, ...)` |
| `None` (legacy) | non-empty | Verbatim | `video_script` (unchanged) |
| `"auto"` | (any value — ignored) | Auto path | `llm.generate_script(video_subject, ...)` |
| `"verbatim"` | non-empty | Verbatim | `video_script` (unchanged) |
| `"verbatim"` | empty/whitespace | ERROR — wizard blocks; backend treats as auto path defensively | n/a |
| `"polish"` | non-empty | Polish path | `llm.polish_script(brief=video_script, ...)` (overwrites `video_script` post-render) |
| `"polish"` | empty/whitespace | ERROR `polish_brief_required` — wizard blocks; backend returns typed error | n/a |

### Lifecycle

- Constructed by the wizard on submit, attached to the `/api/generate` body.
- Passed through to MPT verbatim by the existing `/api/generate` proxy.
- Persisted into `task.json`'s `params` section by MPT's existing serialization.
- Read by `/api/history` for future surface in My Assets (e.g., a "polished" badge — deferred to v2).

### Backwards compatibility

Default `None` triggers FR-008's legacy-compat path: every existing API caller (curl, postman, non-VisualAI clients) sees identical behavior to pre-spec-013. The wizard ships sending explicit values; non-wizard callers keep working unchanged.

---

## Entity 2 — `VideoParams.script_brief` (new field)

**File**: [`app/models/schema.py`](../../app/models/schema.py)
**Cardinality**: one optional value per render request

### Schema (Pydantic v2)

```python
class VideoParams(BaseModel):
    # ... existing fields ...
    script_brief: Optional[str] = None
    # ... existing fields ...
```

### Field-level contract

| Aspect | Value |
|---|---|
| Type | `Optional[str]` |
| Default | `None` |
| Required | No |
| Length | unbounded at the schema layer; wizard warns at ~3000 chars (FR-edge case); LLM prompt budget is the practical cap |

### Validation invariants

1. When `script_mode == "polish"`, the wizard SHOULD send `script_brief` matching the input `video_script` (the creator's typed brief). MPT preserves this verbatim into `task.json`.
2. When `script_mode != "polish"`, the field MUST be `None` or absent. Defensive check in the dispatch can ignore + null it if a caller mistakenly sets it.
3. `script_brief` is NEVER spoken. It's purely provenance / reference data.

### Source-of-truth invariants

- The original creator-typed brief lives in `script_brief`.
- The polished output (what gets spoken) lives in `video_script` AFTER the polish dispatch overwrites it.
- The two fields together let downstream tooling reconstruct: "creator typed X, AI rewrote it as Y."

### Lifecycle

- Constructed by the wizard's submit handler ONLY when `script_mode == "polish"`.
- Passed through `/api/generate` body alongside `video_script`.
- Persisted in `task.json`'s `params` section.
- Read by future tooling (My Assets badge / regenerate-from-brief) — not used in v1 frontend.

---

## Entity 3 — `WizardScriptState` (Layer 1 React state)

**File**: `visualai-frontend/src/lib/script-mode.ts` (new) + `visualai-frontend/src/app/modes/short-video/page.tsx` (state holder)

### TypeScript shape

```ts
export type ScriptMode = "auto" | "verbatim" | "polish";

export interface WizardScriptState {
  mode: ScriptMode;
  // For verbatim + polish: the current textarea content. For auto: ignored.
  text: string;
}

export const PRISTINE_SCRIPT: WizardScriptState = {
  mode: "auto",
  text: "",
};
```

### Helper: `scriptStateToParams`

Translates the wizard state into the wire shape `/api/generate` expects:

```ts
export interface ScriptParams {
  script_mode?: ScriptMode;
  video_script?: string;
  script_brief?: string;
}

export function scriptStateToParams(state: WizardScriptState): ScriptParams {
  switch (state.mode) {
    case "auto":
      return { script_mode: "auto", video_script: "" };
    case "verbatim":
      return { script_mode: "verbatim", video_script: state.text };
    case "polish":
      return {
        script_mode: "polish",
        video_script: state.text,    // backend uses this as `brief`, then overwrites in-place with polished output
        script_brief: state.text,    // also stored separately for provenance
      };
  }
}

export function isPristineScript(state: WizardScriptState): boolean {
  return state.mode === "auto" && state.text === "";
}
```

### State invariants

1. Mode + text persist across forward/back navigation within a wizard session (parent component holds state).
2. Pristine state (`{mode: "auto", text: ""}`) MAY be omitted from the `/api/generate` body entirely — the backend's legacy-compat path handles a missing `script_mode` correctly. The frontend SHOULD always include it for explicitness.
3. Picking Auto MUST NOT clear the typed text from React state — it just hides the textarea. If the creator switches back to Verbatim/Polish, their text reappears. (UX nicety; non-functional.)
4. Picking Polish + clicking Submit on empty `text` MUST trigger an inline error within 100 ms (SC-006). The backend defensively also rejects with `polish_brief_required`.

### Validation rules

- `mode` MUST be one of three documented values; no `null`/`undefined`/empty.
- `text` MUST be a string; trimming applied before submission.

---

## Entity 4 — `polish_script` LLM function I/O

**File**: [`app/services/llm.py`](../../app/services/llm.py) (new function added next to `generate_marketing_script`)

### Function signature

```python
def polish_script(
    brief: str,
    video_subject: str = "",
    duration_seconds: int = 20,
    language: str = "en",
) -> str:
    """Polish a creator's brief into a hook → body → CTA marketing script.

    Args:
        brief: Creator's rough brief — required, non-empty.
        video_subject: Optional product context (typically URL-scraped enriched
            subject from spec 012). When empty, prompt substitutes a sentinel
            string indicating no context.
        duration_seconds: Target script duration (~2.5 words/sec). Defaults to
            20 s; spec 002 will pass through dynamic values when shipped.
        language: Output language code (matches today's auto path's
            ``video_language`` parameter).

    Returns:
        Polished script as plain prose, ready for TTS synthesis.

    Raises:
        ValueError: brief is empty after .strip()
        Any exception from `_generate_response`: surfaced upward by task.py
            as `polish_failed`.
    """
```

### Input invariants

- `brief` non-empty after strip; raises `ValueError` if violated.
- `video_subject` may be empty string; treated as "no context" by the prompt template (R5 of research.md).
- `duration_seconds` ≥ 5; controls `target_words = max(8, duration_seconds * 2.5)`.

### Output invariants

- Plain text (no markdown, no quotes, no parentheticals — enforced by prompt).
- Hook → body → CTA structure (verifiable by reviewing 5 sample outputs against the prompt rules).
- Approximately `target_words` long ± 30%.
- Language matches `language` param (with brief-content translation if needed per prompt constraint #6).

### Error semantics

| Failure | Raises | task.py response |
|---|---|---|
| Empty brief after strip | `ValueError` | `polish_brief_required` (FR-006) |
| OpenAI rate-limit / quota | propagated from `_generate_response` | `polish_failed` (FR-007) |
| OpenAI timeout / network error | propagated | `polish_failed` |
| Empty LLM output (model returned nothing) | `_generate_response` returns empty → `polish_script` raises `ValueError("empty polish output")` | `polish_failed` |

The `polish_script` function does NOT auto-retry — `_generate_response` already has its own retry logic per MPT's existing code path. Adding another retry layer would compound delay without quality gain.

---

## Cross-entity relationships

```text
[creator types brief in Step 3 textarea]
       ↓
[wizard's mode pill set to "Polish"]                          (Entity 3 — WizardScriptState)
       ↓
[scriptStateToParams() composes the wire shape]                (Entity 3 — helper)
       ↓
[/api/generate body includes:]
   - video_subject: <maybe URL-enriched from spec 012>
   - video_script: "rough brief"
   - script_mode: "polish"
   - script_brief: "rough brief"
       ↓
[MPT VideoParams populated]                                    (Entity 1 + Entity 2)
       ↓
[task.py:generate_script() — new dispatch branch]
       ↓
[llm.polish_script(brief, video_subject, ...) called]          (Entity 4)
       ↓
[OpenAI gpt-4o-mini returns polished prose]
       ↓
[task.py overwrites params.video_script with polished output]
       ↓
[task.json serializes:]
   - params.video_subject: <unchanged>
   - params.video_script: "<polished hook→body→CTA>"
   - params.script_mode: "polish"
   - params.script_brief: "rough brief"  ← original preserved
       ↓
[Voice synthesis runs against params.video_script]
       ↓
[Final MP4 voiceover speaks the polished output]
       ↓
[/api/history exposes both video_script + script_brief in the HistoryItem shape (when accessed)]
```

**Source-of-truth invariants**:

- `video_script` ALWAYS contains "what got spoken" — verbatim, auto, or polished. Today's contract preserved.
- `script_brief` ONLY exists for polish mode. Carries the creator's input distinct from the spoken output.
- `script_mode` ALWAYS encodes the creator's explicit choice when the wizard submitted; `None` only when a non-wizard caller hit the API directly (legacy callers).

---

## What is NOT modeled (deliberately)

- **Polish-output history / regeneration**: re-polishing the same brief with a different tone is a v2 follow-up. v1's `script_brief` field is the schema hook that enables it without breaking changes.
- **Tone parameter**: deferred to v2 per plan §Complexity Tracking.
- **Per-tenant default mode**: deferred until debt #2 (tenant context) repays in Step 2.
- **Streaming polish output to the wizard**: deferred per plan §Complexity Tracking.
- **Brief size limits at the schema layer**: wizard warns at ~3000 chars; backend doesn't enforce. v2 may add a hard cap if abuse patterns emerge.

---

## Schema diff summary

For audit clarity:

```diff
# app/models/schema.py — VideoParams class

  class VideoParams(BaseModel):
      # ... existing fields ...
+     script_mode: Optional[Literal["auto", "verbatim", "polish"]] = None
+     script_brief: Optional[str] = None
      # ... existing fields ...
```

That's the entire backend schema delta. Two new optional fields, both default `None`, both backwards-compatible. Spec 013's whole architectural commitment is that adding polish mode requires nothing else on the data layer.
