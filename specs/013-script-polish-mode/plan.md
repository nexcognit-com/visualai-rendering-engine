# Implementation Plan: Polish Mode for Script Editor

**Branch**: `013-script-polish-mode` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/013-script-polish-mode/spec.md`

## Summary

Add a third script mode — **Polish** — to the wizard's Step 3 alongside the existing **Auto** + **Verbatim** behaviors. When the creator picks Polish and types a brief, the LLM rewrites it as a hook → body → CTA marketing script that preserves the creator's facts but recasts structure. The polish pass uses both the brief AND the URL-scraped enriched subject from spec 012 (when present) — brief drives creative direction, subject grounds in factual product context.

Implementation slots into the existing dispatch in [`app/services/task.py:16-39`](../../app/services/task.py#L16-L39) — the `generate_script(task_id, params)` function gains a third branch for `script_mode == "polish"`. New `polish_script(brief, video_subject, duration_seconds, language)` function in [`app/services/llm.py`](../../app/services/llm.py) sits next to the existing `generate_marketing_script` function. Two new optional fields on `VideoParams`: `script_mode` (the discriminator) + `script_brief` (preserved creator input). Both fields default to `None`, preserving today's behavior for legacy callers (FR-008 + FR-010 zero-regression contract).

The wizard's Step 3 gains a 3-pill mode selector ("Auto / Verbatim / Polish") matching the visual language of the Music panel from spec 010. Picking Polish swaps the textarea label + helper text; picking Auto hides the textarea. State persists across forward/backward navigation within the same wizard session.

This is the third "wizard input honesty" feature alongside specs 009 (overlays — pending), 010 (music — shipped), and 012 (URL scraping — shipped). All four make the wizard's input fields do what their labels promise — no more silent reinterpretation.

## Technical Context

**Language/Version**: Python 3.11/3.12 (Layer 3); TypeScript / React (Next.js 16 + React 19) on the frontend.
**Primary Dependencies**:
- **Backend**: existing OpenAI integration in [`app/services/llm.py`](../../app/services/llm.py) — `_generate_response()` plumbing already handles retries, error mapping, model selection (gpt-4o-mini per `config.toml`). NO new Python deps.
- **Frontend**: existing wizard component infrastructure. NO new TS deps. The mode selector reuses Tailwind classes already used by the Music pills from spec 010.
**Storage**: Filesystem only. `task.json`'s `params` section gains `script_mode` and `script_brief` as new optional fields (additive; backwards-compatible).
**Testing**:
- **Backend**: pytest (already set up by spec 010). New file `test/services/test_polish_script.py` with smoke tests for the polish dispatch path + zero-regression for the 2 legacy paths. Mock OpenAI calls via the existing `_generate_response` mock pattern (or use `monkeypatch`).
- **Frontend**: Vitest (set up by spec 012). New file `tests/wizard-mode-selector.test.ts` covering the mode-pill state machine + the legacy-compat default behavior.
**Target Platform**: Existing — Python backend on GPU host (renders), Next.js frontend on Vercel/local.
**Project Type**: Layer 1 + Layer 3 surface, same shape as specs 010 and 012.
**Performance Goals**:
- Polish LLM call adds ≤ 3 s p95 to total render time on a typical Mode 2 render (~80–90 s today). Target derived from `_generate_response` timing on gpt-4o-mini for prompts of comparable length to `generate_marketing_script`.
- Wizard mode-pill click → help-text update ≤ 100 ms (pure local React state).
**Constraints**:
- **No silent fallbacks** on polish failure (FR-007). The render fails closed with `polish_failed`; wizard offers "Try Verbatim instead" as creator-driven recovery.
- **Zero regression** for `script_mode=None` callers (FR-008, FR-010, SC-003). Verified by matched-pair byte-comparison.
- **task.py is debt #5** — adds ONE more dispatch line (third touch) atop the existing two from Step 1 + spec 010-impl. All three touches repay together when Step 3's mode registry lands.
- **Polish prompt lives inline in `llm.py`** — continues debt #4 (Mode 2 prompts inline). Repaid when Step 3's `app/services/modes/` registry lands; polish prompt moves into `app/services/modes/short.py`.
**Scale/Scope**: Mode 2 wizard surface only. Modes 1/3/4/5 inherit the same 3-mode pattern when their wizards ship via their own feature branches.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Reasoning |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | LLM polish work is exactly Layer 3's job (rendering pipeline preprocessing). The wizard surface is Layer 1's job by design. No user/credit/billing logic introduced. |
| **II. Surgical Fork Discipline** | PASS, with continuation of existing debts | Touches **fork-surface files** `app/models/schema.py` (already touched in Step 1 + spec 010 — adds 2 new optional fields) and `app/services/llm.py` (already touched in Step 1 — adds new `polish_script` function). **Touches `app/services/task.py`** for one more dispatch line (third touch — continues debt #5). NO touches to `app/services/material.py`, `app/services/voice.py`, `app/services/video.py`. The five-fork-surface set is respected. |
| **III. Multi-Tenant Context Propagation** | N/A | This feature has no per-render auth surface. The polish call uses the same `_generate_response` plumbing all other LLM calls do; tenant context flows when debt #2 lands. |
| **IV. External Asset Acceptance Over Direct API Calls** | PASS | Uses the existing OpenAI integration in `llm.py`. NO new external API. The OpenAI integration was added in Step 1 and is grandfathered as part of Mode 2's auto path. |
| **V. Mode-Aware Rendering Contract** | PASS, via existing debt | Polish prompt is hardcoded inline in `llm.py` for Mode 2. Continues debt #4 (Mode 2 prompts inline rather than in `app/services/modes/`). When debt #4 repays in Step 3, polish prompt moves into `app/services/modes/short.py` alongside `generate_marketing_script`. |
| **§Technology Constraints — Runtime** | PASS | Python 3.11/3.12; uses existing OpenAI integration. No new dep. |
| **§Technology Constraints — Database** | N/A | No DB; `task.json` is local filesystem. |
| **§Technology Constraints — Observability** | PASS | The new `polish_script` function uses loguru per MPT's existing logging discipline. INFO log on entry/exit + ERROR on failure with `task_id` bound. |
| **§Technology Constraints — Secrets** | PASS | No new API keys. |
| **§Development Workflow — fork-surface PR rule** | APPLIES | This PR touches `app/models/schema.py` + `app/services/llm.py` + `app/services/task.py`. Per the constitution, "PRs touching the five fork-surface files MUST reference the affected Agent Mode(s) and cite the relevant Master Spec section in the PR body." Implementation PR cites Mode 2 + Master Spec §3. |
| **§Development Workflow — pytest gate** | APPLIES | New polish smoke tests MUST exist + pass before merge. |

**Gate result**: PASS. Two existing debts (#4 and #5) each gain one more burndown task. No new debts. Re-check post-Phase 1.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/013-script-polish-mode/
├── plan.md                         # This file
├── research.md                     # Phase 0 — polish prompt design, LLM call placement, brief+subject composition, wizard UI patterns, failure mode mapping, test approach
├── data-model.md                   # Phase 1 — VideoParams.script_mode + VideoParams.script_brief + WizardScriptState + Polish LLM I/O contract
├── quickstart.md                   # Phase 1 — operator runbook covering SC-001 through SC-007
├── contracts/
│   ├── polish-llm-contract.md            # Python function signature + prompt template + error mapping
│   ├── script-mode-wire-shape.md         # VideoParams field semantics + 3-mode dispatch matrix + legacy-compat behavior
│   └── wizard-mode-selector-contract.md  # UI state machine + pill-button visual contract + persistence rules
├── checklists/
│   └── requirements.md             # Spec quality checklist (already created)
├── spec.md                         # Feature specification (clarified 2026-05-02)
└── tasks.md                        # Phase 2 — produced by /speckit-tasks (NOT here)
```

### Source code changes (Layer 3 — this repo)

```text
app/
├── models/
│   └── schema.py                   # MODIFIED: add Optional[Literal["auto","verbatim","polish"]] = None for script_mode + Optional[str] = None for script_brief on VideoParams
├── services/
│   ├── llm.py                      # MODIFIED: new polish_script(brief, video_subject, duration_seconds, language) function — ~50 lines including prompt template
│   └── task.py                     # MODIFIED: new dispatch branch in generate_script() — third touch line continuing debt #5
└── (everything else)               # UNTOUCHED — material.py, voice.py, video.py stay rebase-clean
test/
└── services/
    └── test_polish_script.py       # NEW: smoke tests for polish dispatch + 3 mode behaviors + legacy-compat
```

**Files explicitly NOT touched**:
- `app/services/material.py` — Principle II (kept rebase-clean)
- `app/services/voice.py` — Principle II
- `app/services/video.py` — Principle II
- Anything else in `app/` outside the three files listed above

### Source code changes (Layer 1 — `visualai-frontend/`)

```text
visualai-frontend/src/
├── lib/
│   └── script-mode.ts              # NEW — TS types (ScriptMode, WizardScriptState) + helpers (PRISTINE_SCRIPT, scriptStateToParams)
└── app/
    ├── api/
    │   └── generate/
    │       └── route.ts            # MODIFIED — pass script_mode + script_brief through to MPT (alongside existing video_subject + video_script + bgm_*)
    └── modes/short-video/
        └── page.tsx                # MODIFIED — Step 3 gains 3-pill mode selector + dynamic textarea label/help text + state persistence + "Try Verbatim instead" fallback for polish_failed errors
visualai-frontend/tests/
└── wizard-mode-selector.test.ts    # NEW — Vitest tests for the mode-pill state machine + legacy-compat default behavior
```

**Structure Decision**: Layer 1 changes localize to one wizard file + one new lib + one new test. Layer 3 changes localize to three fork-surface files (one new function each in schema/llm; one new dispatch line in task). Total footprint ≤ 200 lines of code. Mirrors specs 010 + 012's incremental delivery shape.

## Cross-spec coordination

| Other spec | Shared file with this spec | Conflict? |
|---|---|---|
| Spec 010 (music control — shipped) | `visualai-frontend/src/app/modes/short-video/page.tsx` (wizard) | No semantic conflict — Music panel lives in Step 3's lower half; mode-selector pills land at the top of Step 3. Different JSX subtrees. Visual style reused (pills match). |
| Spec 010 (music control — shipped) | `app/models/schema.py` | No conflict — adds two new fields (`script_mode`, `script_brief`); spec 010 added none (used existing bgm_* fields). |
| Spec 012 (URL scraping — shipped) | `visualai-frontend/src/app/api/generate/route.ts` | No conflict — spec 012 added the optional `music` field passthrough; this spec adds `script_mode` + `script_brief` passthrough. Both extend the same body builder cleanly. |
| Spec 012 (URL scraping — shipped) | The polish prompt explicitly references `video_subject` (which now carries the URL-scraped enriched subject) | No code conflict; behavioral integration documented in clarify Q1 + FR-005. The polish prompt receives both the brief and the enriched subject as separate template inputs. |
| Spec 002 (duration — pending) | `app/services/llm.py` `polish_script` function signature | Spec 013 hardcodes `duration_seconds=20`; spec 002 ships dynamic duration. When spec 002 lands, the wizard's mode-selector layer just passes the slider value through. No spec 013 changes needed. |
| Spec 011 (BGM audit — pending, not yet implemented) | None | Independent; ships in different files. |

The implementation order is a non-issue between 013 and any of 002 / 011 / 009 — different files. With 010 and 012 already shipped, 013 lands cleanly.

## Complexity Tracking

> No NEW Constitution violations. Section minimal.

This feature deliberately rejects four heavier alternatives:

- **Polish prompt as a first-class mode-registry entry at v1** — rejected. The mode-registry redesign is Step 3 territory; tackling it now would balloon scope. Polish prompt lives inline in `llm.py` (continues debt #4), repaid when the registry lands.
- **Auto-fallback to Verbatim on polish failure** — rejected per FR-007 + the spec-009/010/011/012-established discipline of "no silent fallbacks." Polish failure surfaces a typed `polish_failed` error and the creator picks the next move.
- **Streaming the polished script to the wizard while the LLM generates** — rejected. The 1-3 s p95 polish call is fast enough that the existing "Submitting…" wizard UX is fine. Streaming adds significant frontend complexity for negligible perceived benefit.
- **A "Tone" sub-selector under Polish** (formal / conversational / punchy) — rejected at v1. The polish prompt defaults to the same direct-response tone Mode 2's existing `generate_marketing_script` uses, for consistency. Adding tone is a low-risk v2 follow-up that doesn't require schema changes (just a new optional field).

## Re-evaluation post-Phase 1

After data-model + contracts + quickstart land, re-check:

- **Principle I**: still PASS — Layer 3 LLM work, Layer 1 wizard UI.
- **Principle II**: still PASS — three fork-surface files touched (schema, llm, task), all already in the existing debt set; `material.py` / `voice.py` / `video.py` untouched.
- **Principle V**: still PASS — debt #4 continuation; no new debt.
- **Zero-regression for legacy callers**: enforced via `script_mode=None` defaults + matched-pair test in quickstart Part 1.

The post-design check has nothing new to flag. Plan is implementation-ready.
