# Implementation Plan: Video Duration Range, Variations, and Preview Gate for Long Videos

**Branch**: `002-video-duration-variations` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from [/specs/002-video-duration-variations/spec.md](spec.md)

## Summary

Three interlinked capabilities coordinated across three layers of the VisualAI stack:

1. **Duration control** — user-selectable video length 5–90 s with ±1 s rendered tolerance. Replaces the current implicit duration (derived from script + voice length) with an explicit top-level parameter.
2. **Variations** — N ∈ {1, 2, 3} distinct renders per click, seeded differently to produce diverse B-roll / script / music selections from one input set.
3. **Preview gate** — for duration > 30 s the system first renders N × 5-second previews (literal first 5 s of the intended full render), holds the full-render credits, and only debits on user approval.

Technical approach: extend this repo's `VideoParams` Pydantic model with four new fields (`total_duration_seconds`, `variation_count`, `render_mode`, `seed`); extend the `/api/v1/videos` controller to branch on `render_mode`; introduce a shared random-seed propagation path through `llm.py → voice.py → material.py → video.py` so preview and full renders are visually identical in their first 5 s. Credit hold/debit/release lifecycle is implemented in Layer 2 (Orchestration API), not in this repo (per constitution Principle I). Frontend exposes a slider, a variation stepper, and a preview-approval grid composed from the design tokens and components defined in spec 001.

## Technical Context

**Language/Version**:
- Layer 3 (this repo): Python 3.11–3.12 (per constitution)
- Layer 1 (frontend): TypeScript 5.x on Next.js 15 App Router
- Layer 2 (orchestration — Step 2 prerequisite): Python 3.11 / FastAPI or Node.js — selected in spec 003 (future)

**Primary Dependencies**:
- Layer 3: Pydantic 2.x (existing), MoviePy 2.1.2 (existing), Faster-Whisper 1.1.0 (existing), Loguru 0.7.3 (existing). No new Python deps.
- Layer 1: shadcn/ui components `Slider`, `Input`, `Button`, `Card`, `Progress`, `Dialog` (Radix primitives); TanStack Query for polling; Zustand for wizard state. All installed during spec 001 implementation.

**Storage**:
- Layer 3: transient filesystem under `storage/tasks/<task_id>/` (existing convention). No schema changes.
- Layer 2 (future, NOT in this feature): PostgreSQL credit ledger tables — owned by a separate credit-ledger feature spec. This spec defines the contract, not the storage.
- Redis: existing use for task state. Extended with one optional key per variation for preview/full linkage.

**Testing**:
- Layer 3: pytest (existing `test/services/` layout). Adds contract tests for `render_mode={preview|full}` and integration test for duration tolerance.
- Layer 1: Playwright component + E2E; Vitest or Jest for unit.

**Target Platform**:
- Layer 3 runtime: Linux + GPU (RunPod or equivalent) in production; Docker Compose for local dev.
- Layer 1 runtime: evergreen browsers (Chrome, Firefox, Safari latest 2; Edge latest 1).

**Project Type**: Web application (separate frontend + backend). This plan touches all three layers but ships scoped-down per-layer slices.

**Performance Goals**:
- Short-path (duration ≤ 30 s, N = 3 variations): all three full renders delivered within ≤ 3 minutes wall-clock on a single GPU host.
- Preview-gate path (duration > 30 s, N = 3 variations): three 5-second previews delivered within ≤ 45 seconds; after approval, full renders within ≤ 5 minutes.
- Duration tolerance: rendered MP4 playable runtime within ± 1 second of requested (frame-rounded).

**Constraints**:
- Preview and full must derive from identical `seed` + identical inputs; first 5 s perceptual similarity ≥ 90 % (SC-005).
- Credit-hold semantics must be atomic (hold → partial debit → release). Atomicity lives in Layer 2; Layer 3 emits state-change events that Layer 2 acts on.
- Layer 3 code changes confined to the five fork surfaces per Principle II (`schema.py`, `llm.py`, `voice.py`, `material.py`, `app/controllers/`).
- No direct database access from Layer 3 (Principle I).

**Scale/Scope**:
- Phase 1 target (per Master Spec §9): 100 paying users, avg 3+ generations/week → ~300 generations/week upper bound. Single-host GPU capacity plan; no horizontal scaling required for this feature.
- Renders per generation: up to 3 × preview (5 s each) + up to 3 × full (5–90 s each) per user click on long-video path.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Cross-referenced against the 5 principles in [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0.

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only** (NON-NEGOTIABLE) | ✅ PASS | All credit hold/debit/release logic, user approval state machine, and variation dispatch live in Layer 2. This repo only accepts `render_mode` + `seed` + `total_duration_seconds` and produces assets. |
| **II. Surgical Fork Discipline** | ✅ PASS | All Python edits land inside the five permitted surfaces. No new top-level module. No `app/services/modes/` registry created here — that's Step 3 per the 5-step build plan; this feature uses inline constants for now and is flagged in `STEP1_DEBT.md` extension. |
| **III. Multi-Tenant Context Propagation** | ⚠ PARTIAL | `VideoParams` in Step 1 does not yet carry `tenant_id` / `user_id` (that's Step 2). For Mode 2 tonight, this feature targets single-tenant localhost; multi-tenant fields get added alongside JWT middleware in Step 2. Flagged in `STEP1_DEBT.md`. |
| **IV. External Asset Acceptance Over Direct API Calls** | ⚠ PARTIAL (Step 1 only) | Step 1 uses Pexels direct fetch for Mode 2 B-roll (tracked debt). Step 3 rewrites `material.py` to accept pre-signed URLs from Layer 2. This feature's `seed` propagation works with either path. No regression. |
| **V. Mode-Aware Rendering Contract** | ✅ PASS | Duration and variation parameters are mode-orthogonal. Mode 3 (Long-Form, 2–5 min) is explicitly out of this feature's scope and retains its own pipeline. Feature applies to Modes 1, 2, 4, 5. |

**Violations**: none. The two PARTIAL entries reflect tracked Step 1 debts from the 5-step build plan, not constitutional violations — the debt is scheduled for Step 2/3 repayment and recorded in [`STEP1_DEBT.md`](../../STEP1_DEBT.md) (file to be created in Step 1 per the overall plan).

**Complexity justification required**: no.

## Project Structure

### Documentation (this feature)

```text
specs/002-video-duration-variations/
├── spec.md              # /speckit-specify output (done)
├── checklists/
│   └── requirements.md  # /speckit-specify validation (done)
├── plan.md              # this file
├── research.md          # Phase 0 output (this run)
├── data-model.md        # Phase 1 output (this run)
├── quickstart.md        # Phase 1 output (this run)
├── contracts/
│   ├── layer3-videos-api.md       # Layer 3 HTTP contract
│   ├── layer2-to-layer3.md        # Orchestration → Rendering contract
│   └── frontend-components.md     # UI component prop contracts
└── tasks.md             # /speckit-tasks output (next command — NOT produced here)
```

### Source Code (repository root + sibling frontend repo)

```text
# Layer 3 — this repository
app/
├── models/
│   └── schema.py                 # EDIT: add total_duration_seconds, variation_count, render_mode, seed
├── services/
│   ├── llm.py                    # EDIT: accept seed; produce deterministic script for same seed+inputs
│   ├── voice.py                  # EDIT: accept seed; deterministic voice synthesis (voice choice, rate) — already deterministic for Azure/Edge
│   ├── material.py               # EDIT: accept seed; deterministic B-roll selection; support render_mode=preview (first-5s pool only)
│   ├── video.py                  # EDIT: accept total_duration_seconds; enforce ±1s tolerance; preview mode truncates assembly
│   └── task.py                   # EDIT: branch preview vs full render path
└── controllers/
    └── v1/
        └── video.py              # EDIT: accept new fields; dispatch per render_mode

test/
└── services/
    ├── test_duration_tolerance.py       # NEW: produced MP4 within ±1s of request
    ├── test_preview_equivalence.py      # NEW: first 5s of full render ≈ preview render (SC-005)
    ├── test_variation_diversity.py      # NEW: N variations produce N distinct assets
    └── test_render_mode_contract.py     # NEW: controller accepts & validates new fields

# Layer 1 — sibling repo at ../visualai-frontend/
src/
├── components/
│   └── wizard/
│       ├── DurationSlider.tsx           # NEW: 5–90s range, slider + numeric
│       ├── VariationStepper.tsx         # NEW: 1/2/3 selector next to Generate CTA
│       ├── PreviewApprovalGrid.tsx      # NEW: per-variation video player + Approve/Reject
│       └── GenerationProgress.tsx       # EDIT (from spec 001 build): add per-variation tracks
├── hooks/
│   ├── useGenerationJob.ts              # NEW: polling, state machine wrapper
│   └── useCreditEstimate.ts             # NEW: compute preview+full cost per mode+duration+N
├── lib/
│   └── api/
│       └── generate.ts                  # EDIT: send new fields; fetch variation status
└── stores/
    └── wizardStore.ts                   # EDIT: hold duration, variation_count, per-variation state

e2e/
└── long-video-preview-gate.spec.ts      # NEW: end-to-end scenario for US3
```

**Structure Decision**: Web application — `app/` (Python rendering engine) remains in this repository; `src/` (Next.js frontend) lives in the sibling `../visualai-frontend/` repository. Layer 2 Orchestration API is a prerequisite (Step 2 of the 5-step build plan) and is **not produced by this feature** — this feature publishes the contract that Layer 2 must implement.

## Complexity Tracking

No justified violations. The two PARTIAL items in the Constitution Check are pre-existing Step 1 debts, not new complexity introduced by this feature.

## Phase 0 — Research (resolved in [research.md](research.md))

All NEEDS CLARIFICATION items in Technical Context are resolved via the spec's Assumptions section or via research below. Phase 0 focuses on four questions that materially shape the design:

1. How do we make preview and full render *visually equivalent in their first 5 s* for the same inputs?
2. How do we produce *perceptually distinct* variations from the same inputs?
3. How does Layer 2 enforce the credit-hold / partial-debit / release lifecycle atomically?
4. What's the minimum change to MPT's existing `video.py` to support a hard total-duration target?

Phase 0 output: [research.md](research.md).

## Phase 1 — Design & Contracts

**Prerequisites**: Phase 0 complete.

Phase 1 output artifacts (produced in this run):
- [data-model.md](data-model.md) — entities: VideoJob, Variation, CreditHold, PreviewAsset.
- [contracts/layer3-videos-api.md](contracts/layer3-videos-api.md) — HTTP contract for `POST /api/v1/videos` with the four new fields; status endpoint contract.
- [contracts/layer2-to-layer3.md](contracts/layer2-to-layer3.md) — orchestration-to-rendering request/response shapes, error semantics, retry policy.
- [contracts/frontend-components.md](contracts/frontend-components.md) — TypeScript prop types for `DurationSlider`, `VariationStepper`, `PreviewApprovalGrid`, and the `useGenerationJob` hook.
- [quickstart.md](quickstart.md) — localhost run steps to exercise the feature end-to-end once Step 1 frontend and Layer 2 stub are available.

Agent context update: [`.specify/scripts/bash/update-agent-context.sh claude`](../../.specify/scripts/bash/update-agent-context.sh) executed after Phase 1 artifacts land (this run).

**Post-design re-check**: Constitution Check re-evaluated against the produced contracts and data model — still ✅ PASS on Principles I, II, V; still ⚠ PARTIAL (Step 1 debt, unchanged) on III and IV. No new complexity introduced.
