# Step 1 Debt — tracked principle relaxations

**Created**: 2026-04-21 (as part of the Step 1 Mode 2 MVP)
**Owner**: Layer 3 rendering engine (this repo)
**Authority**: [.specify/memory/constitution.md](.specify/memory/constitution.md) v1.0.2 + the 5-step build plan

Step 1 of the VisualAI 5-step build plan ships **Mode 2 (Short Marketing Video)** end-to-end on the existing MoneyPrinterTurbo engine before the full 5-layer architecture is in place. Doing this cleanly tonight requires consciously relaxing four constitution principles. Each relaxation is scheduled for repayment in a specific later step; this file is the single source of truth for what's owed and to whom.

| # | Principle | Step-1 relaxation | Repays in | Burn-down commit touches |
|---|---|---|---|---|
| 1 | **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | The Next.js frontend (`../visualai-frontend/`) calls this Layer 3 API directly at `http://localhost:8080/api/v1/videos` because Layer 2 (Orchestration API) does not exist yet. | **Step 2** | Stand up `../visualai-orchestration/` FastAPI service; frontend routes all calls through it; Layer 3 accepts only requests proxied via Layer 2 |
| 2 | **III. Multi-Tenant Context Propagation** | Step-1 requests omit `tenant_id`, `user_id`, `product_id`, and `generation_id`. No JWT middleware runs on the video controllers. Mode 2 renders succeed without any tenant context. | **Step 2** | Extend `VideoParams` with required tenant fields; add JWT middleware to `app/controllers/v1/video.py`; flip a feature flag `REQUIRE_TENANT_CONTEXT=true` |
| 3 | **IV. External Asset Acceptance Over Direct API Calls** | Mode 2 B-roll is fetched directly from Pexels via the existing `app/services/material.py`. The constitution permits Pexels only inside Mode 5 (Faceless Channel Automation); here we stretch it to Mode 2 to avoid a `material.py` rewrite tonight. | **Step 3** | Rewrite `app/services/material.py` to accept pre-signed URLs from Layer 2; gate retained Pexels integration behind `mode == "faceless"` only |
| 4 | **V. Mode-Aware Rendering Contract** | Mode 2 prompt templates live as an inline function (`generate_marketing_script`) in `app/services/llm.py`. There is no `app/services/modes/` registry yet. The `VideoParams.mode` field accepts only `"faceless"` (default) and `"short"`. | **Step 3** | Build `app/services/modes/` registry; migrate `generate_marketing_script` into `app/services/modes/short.py`; add `app/services/modes/product_shoot.py` (Mode 1), `app/services/modes/faceless.py` (Mode 5); widen the enum only as each mode lands |

## Principle II (Surgical Fork Discipline) is NOT relaxed

Step 1 only touches two files inside the five permitted fork-surface set:
- [`app/services/llm.py`](app/services/llm.py) — new `generate_marketing_script()` function appended; existing `generate_script()` untouched.
- [`app/models/schema.py`](app/models/schema.py) — new optional `mode: Literal["faceless", "short"]` field on `VideoParams`, defaulted so upstream behavior is preserved.

No other MPT source file in this repo is modified during Step 1. `ops/neon/migrations/` files added by feature 003 are Layer 4 DDL artifacts and fall under the §Technology Constraints Database exception.

## How the debt is tracked

- **Step 2** opens with a checklist task reading "burn down Step 1 debts #1 and #2" and MUST not close without updating this file.
- **Step 3** opens with a checklist task reading "burn down Step 1 debts #3 and #4" and MUST update this file to remove the repaid rows.
- When a row is repaid, strike it through (not delete) and add a `repaid in <commit sha>` note on the same line. The file preserves the full history of every temporary constitutional exception.

## When this file should be empty

Once all four rows are struck through, Step 1's debt is fully retired. At that point `STEP1_DEBT.md` SHOULD be deleted in the same commit that retires the final debt, with the commit message citing all four repayment references.

## Cross-references

- [VisualAI by NexCognit — Master Product Specification](VisualAI%20by%20NexCognit%20%E2%80%94%20Master%20Product%20Specification.md)
- [Constitution v1.0.2](.specify/memory/constitution.md)
- [Spec 001 — UI Style](specs/001-nexcognit-ui-style/spec.md) (frontend design system consumed by Step 1)
- [Spec 002 — Video Duration / Variations / Preview Gate](specs/002-video-duration-variations/spec.md) (preview-gate itself is Step 2+; Step 1 ships single-variation only)
- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md)
