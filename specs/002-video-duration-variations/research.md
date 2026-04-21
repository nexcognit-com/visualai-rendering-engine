# Research: Video Duration Range, Variations, and Preview Gate

**Phase**: 0 — Research
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This document resolves the four open design questions flagged in Phase 0 of the plan. Each question follows the Decision / Rationale / Alternatives format.

---

## Q1. How do we guarantee preview and full render are visually equivalent in their first 5 seconds?

**Decision**: Thread a single `seed: int` parameter from the API call into every stochastic step of the pipeline: LLM script generation, B-roll candidate ordering/selection, voice line-break segmentation, music clip selection, and subtitle positioning. Preview and full render for the same `seed + inputs` produce identical decisions; the preview pipeline simply truncates output at t = 5 s.

**Rationale**:
- MPT's existing pipeline is already deterministic for TTS (Azure / Edge return the same audio for the same text + voice + rate). The only non-determinism today lives in LLM generation (temperature > 0 is non-deterministic by default) and Pexels B-roll selection (random shuffling of candidate pool).
- Threading a single seed is a single small change per file rather than a re-architecture. It lets FR-012 ("preview is literal first 5 s") be a true invariant rather than a best-effort similarity.
- Perceptual similarity check (SC-005 ≥ 90 %) becomes a regression test: given the same seed + inputs, the first 5 s of a full 60 s render must produce byte-identical audio and near-identical video frames (minor codec variance tolerated) compared with a preview-only render.

**Alternatives considered**:
- *Separate preview prompt templates* — rejected. Creates a second source of truth; user's judgment of the preview wouldn't predict the full render.
- *Render the full video first, then truncate to 5 s for the preview* — rejected. Defeats the cost-saving purpose (SC-004); full render is what we're trying to avoid paying for.
- *Cache the first 5 s of any generation and replay it* — rejected. Works but double-stores assets; adds cache-invalidation complexity; seed-propagation is simpler and already needed for variations (Q2).

---

## Q2. How do we produce perceptually distinct variations from the same inputs?

**Decision**: The N variations use `seed_set = [seed_base + i for i in range(N)]`. Seed variance propagates through the same four stochastic steps identified in Q1. For LLM script generation, the seed also maps to one of three rhetorical variants held inline: "hook-first," "question-first," "statistic-first." For B-roll, the seed controls which ordered subset of the Pexels result pool is consumed. For voice, the seed selects among the mode-approved voices if more than one is listed; it does NOT alter user-chosen voice. For music, the seed picks from the mode-approved BGM pool.

**Rationale**:
- Seed-based divergence is cheap and matches what users expect from "give me 3 variations" UX.
- Keeping the variation logic inside the deterministic pipeline (rather than re-querying the LLM with random temperature) means every variation is reproducible — important for debugging customer complaints and for the preview-to-full equivalence invariant (Q1).
- Three variants × three stochastic surfaces gives at least 27 possible combinations per input before we exhaust novelty; more than enough for N ≤ 3.
- Addresses the "all variations look the same" edge case in the spec: if `seed_base + 0` and `seed_base + 1` collapse to the same rhetorical variant for a given prompt, the UI offers "Regenerate with stronger diversity," which reseeds at `seed_base + 100 + i` and retries the three stochastic surfaces at no preview cost.

**Alternatives considered**:
- *Temperature sweep (LLM temp = 0.3, 0.7, 1.1)* — rejected. Violates reproducibility; two re-runs of the same job return different assets, which breaks the preview-to-full invariant and audit trails.
- *Ask the LLM for "3 variants in one call"* — rejected. Expensive token use, and locks all three variants into a single LLM response, so a partial failure loses all three. Parallel single-prompt calls with distinct seeds are more resilient.
- *Let the user pick which axis to vary (script vs footage vs voice)* — rejected for v1. Deferred to a future feature; default three-axis variation covers the "I want something different" intent well enough.

---

## Q3. How does Layer 2 enforce the credit-hold → partial-debit → release lifecycle atomically?

**Decision**: Layer 2 implements a state machine per `VideoJob` with four credit events, persisted in a single `credit_transactions` table (Master Spec §6) using a single-row UPDATE per transition guarded by the row's current state. Event ordering:

1. `hold(N × full_cost)` on job submission.
2. `debit(N × preview_cost)` immediately after previews are requested (this debit is unconditional).
3. On user decision for each variation:
   - `debit((full_cost − preview_cost))` on Approve (or `debit(full_cost)` if previews were free for that mode; policy-configurable).
   - `release(full_cost − preview_cost)` on Reject.
4. On job auto-expire (24 h idle): `release` all remaining unused portion of the hold.

Each transition is a single DB transaction with `UPDATE credit_holds SET state=... WHERE id=? AND state=?` — ensuring exactly-once semantics without distributed-transaction coordinators.

Layer 3 (this repo) emits Redis events (`video_job:<id>:preview_ready`, `video_job:<id>:approved:<variation_idx>`, `video_job:<id>:full_ready:<variation_idx>`, `video_job:<id>:failed:<variation_idx>`). Layer 2 consumes these and calls its own credit state-machine API. Layer 3 NEVER calls credit APIs directly (per constitution Principle I).

**Rationale**:
- Single-row state transitions avoid the need for 2PC, sagas, or a workflow engine. Neon PostgreSQL guarantees atomic UPDATEs.
- Redis pub/sub is already used in MPT for task progress; adding named events is a zero-dependency extension.
- Separation of concerns matches the 5-layer architecture: Layer 3 emits facts, Layer 2 enforces policy.
- 24-hour auto-expire is implemented as a background job in Layer 2 that scans for `awaiting_approval` holds with `created_at < NOW() - 24h` and transitions them to `expired` with a single UPDATE.

**Alternatives considered**:
- *Two-phase commit between Layer 2 and Layer 3 DBs* — rejected. Overkill; creates operational burden; Layer 3 has no DB anyway per Principle I.
- *Event sourcing with a full audit trail* — rejected for v1. Credit_transactions table already gives per-event history; event sourcing is a future upgrade if needed for compliance.
- *Synchronous Layer 3 → Layer 2 RPC on every state change* — rejected. Tight coupling; an outage in Layer 2 would block rendering. Async via Redis keeps Layer 3 rendering capacity decoupled from Layer 2 availability.

---

## Q4. What's the minimum change to MPT's existing `video.py` to support a hard total-duration target?

**Decision**: MPT's current pipeline produces a video whose total duration is the sum of generated voice-over length + trailing music padding. The new invariant (5–90 s ± 1 s) is enforced by:

1. **Script length control**: LLM prompt in `llm.py` includes "Target length: {target_duration} seconds, ≈ {target_duration × 2.5} words" instruction; target word count is computed at `2.5 words/second` (conservative English average).
2. **Voice-over trim/pad**: After Azure/Edge TTS returns the audio, a post-processing step in `voice.py` either trims silence from the tail to hit target length, or pads with 0.5 s of music-only (already part of MPT BGM mix) to reach target length. Trim tolerance: ± 0.5 s silence-detection threshold.
3. **Final assembly**: `video.py` builds the video at exactly `target_duration_seconds` using the post-processed audio track as the master timeline. B-roll clips are fitted to this timeline (existing MoviePy behavior). Preview mode: same assembly but cut at t = 5 s.

Duration tolerance ± 1 s is achievable because: voice trim ± 0.5 s + assembly rounding to nearest frame (~0.04 s at 24 fps) << 1 s.

**Rationale**:
- MPT already computes audio length and aligns video to it. The change is a small shift: instead of "video length = whatever the LLM produced," the LLM produces text sized for a known target, and post-processing rounds to the exact target.
- All three changes live inside already-modified fork-surface files (`llm.py`, `voice.py`, `video.py`) per Principle II.
- No new dependency; MoviePy supports `.subclip(0, 5)` for preview truncation.

**Alternatives considered**:
- *Fixed voice-over speed adjustment (speed up / slow down)* — rejected. Produces unnatural audio for large deltas; Azure Neural voices in particular sound jarring when sped up.
- *Stretch/compress via FFmpeg atempo filter* — rejected. Same unnaturalness; only useful for ≤ 5 % delta.
- *Accept wider tolerance (± 3 s)* — rejected. Spec requires ± 1 s; wider tolerance defeats the purpose of precise duration control for ad-format constraints (TikTok counts 15 s exactly; ≥ 16 s gets re-categorized).

---

## Summary

All four Phase-0 questions resolved. No unresolved NEEDS CLARIFICATION items remain. Key design choices carried into Phase 1 contracts:

- **Seed is the single source of randomness** threaded through LLM, voice (voice-selection only, not rate/volume), B-roll, music, subtitle positioning.
- **Variations are N parallel seeded jobs**, not one multi-variant LLM call.
- **Credit state machine lives in Layer 2**, driven by Redis events emitted by Layer 3.
- **Duration enforcement combines LLM word-count sizing + voice trim/pad + assembly timeline fit** — all within the five permitted fork-surface files.
