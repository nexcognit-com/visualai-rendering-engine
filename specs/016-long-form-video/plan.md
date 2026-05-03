# Implementation Plan: Mode 3 — Long-Form Video Generator (16:9 YouTube, 2-5 min)

**Branch**: `016-long-form-video` | **Date**: 2026-05-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/016-long-form-video/spec.md`

## Summary

Mode 3 produces 2–5 minute YouTube-style explainers (16:9, 1080p, narration + B-roll + lower-third subtitles + optional BGM) by extending the patterns shipped for Mode 2 (Short Marketing Video) and Mode 1 (Product Shoot Generator). Three surfaces:

- **Layer 3 (this repo)**: a new mode entry in `app/services/modes/long_form.py` with the script scaffold, duration/aspect-ratio/subtitle-position config; a small extension to `generate_long_form_script` in `app/services/llm.py`; an additional literal value in `VideoParams.mode` in `app/models/schema.py`.
- **Layer 2 (`visualai-orchestration`)**: new `POST /api/v1/long-form-videos`, `GET /api/v1/long-form-videos`, `GET /api/v1/long-form-videos/{id}` endpoints; a JSON-file `long_form_store.py` (mirrors spec 015's `product_shoot_store.py` Step-3 stand-in); pre-signed URL handoff to/from Layer 3.
- **Layer 1 (`visualai-frontend`)**: new dashboard card; a 3-step wizard at `/modes/long-form/`; an API proxy at `/api/long-form-videos`; My Assets gains a Long-Form heterogeneous card variant.

No new runtime dependency. URL-source path reuses spec 012's scraping endpoint. Music selection reuses spec 010. Brand overlays inherit from spec 009 if user has uploaded brand assets.

## Technical Context

**Language/Version**: Python 3.11/3.12 (Layer 3 + Layer 2); TypeScript / React (Next.js 16 + React 19) on Layer 1.
**Primary Dependencies**: MoviePy + FFmpeg + ImageMagick (already pinned upstream — Layer 3 stitches narration + B-roll + subtitles); FastAPI + httpx + pydantic-settings + loguru (Layer 2 — already in spec 015's PR-A); Next.js Form/FormData + lucide-react (Layer 1 — already used by Mode 1/2 wizards).
**Storage**: JSON-file store at `storage/tasks/lf_<id>/record.json` in Layer 2 (mirrors spec 015's `product_shoot_store.py`); Layer 3 emits the assembled MP4 to its existing `storage/tasks/<task_id>/final-1.mp4` path; Layer 2 pre-signs and serves it. Step-4 swap to a Neon `long_form_generations` table happens later — same record shape.
**Testing**: pytest in Layer 3 (mode registry unit tests + smoke test exercising the long-form script path with mocked LLM/voice/B-roll); pytest + respx in Layer 2 (route tests mirror `tests/routes/test_product_shoots.py` from spec 015); component-level smoke for the Layer 1 wizard.
**Target Platform**: GPU-capable host (RunPod or equivalent) for Layer 3 render; FastAPI on Layer 2; Vercel-style Next.js on Layer 1.
**Project Type**: Three-tier web service (Layer 3 render engine + Layer 2 orchestration API + Layer 1 frontend), continuing the architecture from specs 014/015.
**Performance Goals**: SC-001: median wall-clock ≤ 5 minutes for the 3-minute target; SC-005: cost per generation ≤ $0.50 USD (median).
**Constraints**: 1080p ceiling for v1 (no 4K); ±15s on actual vs target duration (FR-017, SC-002); subtitles bounded to lower-third region (75%–90% of frame height) for 100% of frames (SC-003); demo-bearer auth in Step-3 (FR-015); record persistence survives Layer 2 restarts (lessons learned from spec 015's in-memory v1).
**Scale/Scope**: v1 single-user demo; ~100 generations/day target. Step 4 multi-tenant via spec 014 will revisit limits.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only** | ✅ Pass | Mode 3 logic lives in the mode registry + small llm.py/schema.py extensions. Auth, credit ledger, user CRUD — none of these enter this repo. |
| **II. Surgical Fork Discipline** | ✅ Pass | All Layer 3 changes confined to the six approved surfaces: new file in `app/services/modes/`, additive edits in `app/services/llm.py`, additive edit in `app/models/schema.py`. No core MoviePy/FFmpeg edits. |
| **III. Multi-Tenant Context Propagation** | 🟡 Acknowledged debt | Mode 3 ships against the demo-tenant Step-3 layer (same as Modes 1/2/5 today). Spec 014 closes this debt across all modes. Documented in spec.md "Assumptions" + this plan's Complexity Tracking. |
| **IV. External Asset Acceptance Over Direct API Calls** | ✅ Pass | Layer 3 receives pre-signed B-roll URLs from Layer 2.5; no AI provider calls from Layer 3. Mode 5's Pexels exemption stays scoped to Mode 5. |
| **V. Mode-Aware Rendering Contract** | ✅ Pass | Mode 3 is one of the five reserved modes. Its prompt templates, script length bounds, aspect ratio (16:9), and subtitle positioning (lower-third) live in `app/services/modes/long_form.py`. No drift across service files. |

**No constitution amendments required.** Mode 3 was already reserved in v1.1.0; this spec realises it.

## Project Structure

### Documentation (this feature)

```text
specs/016-long-form-video/
├── plan.md              # this file
├── spec.md
├── research.md          # phase 0 — provider/tooling decisions for long-form
├── data-model.md        # phase 1 — LongFormGeneration entity + ScriptSegment
├── quickstart.md        # phase 1 — end-to-end smoke walkthrough
├── contracts/
│   ├── layer2-long-form-api.md    # POST/GET/LIST /api/v1/long-form-videos
│   ├── layer3-render-contract.md  # mode="long" extensions to /api/v1/videos
│   └── layer1-wizard-contract.md  # wizard ↔ API proxy contract
└── tasks.md             # phase 2 — produced by /speckit.tasks (NOT this command)
```

### Source Code (repository root)

This is a multi-repo plan. The actual code lands in three repos:

```text
# Layer 3 — this repo (MoneyPrinterTurbo fork)
app/
├── services/
│   ├── modes/
│   │   └── long_form.py        # NEW — registry entry: prompt template, durations, aspect ratio, subtitle position
│   └── llm.py                  # EDIT — add generate_long_form_script()
├── models/
│   └── schema.py               # EDIT — extend VideoParams.mode literal: add "long"
└── controllers/
    └── (existing video routes — already mode-dispatch, no edit)

test/
└── services/
    └── modes/
        └── test_long_form.py   # NEW — registry contract test

# Layer 2 — sibling repo: visualai-orchestration
app/
├── routes/
│   └── long_form_videos.py     # NEW — POST/GET/LIST endpoints
├── services/
│   └── long_form_store.py      # NEW — JSON-file store (mirrors product_shoot_store.py)
└── models/
    └── long_form.py            # NEW — LongFormGeneration Pydantic model

tests/
└── routes/
    └── test_long_form_videos.py  # NEW — mirrors test_product_shoots.py

# Layer 1 — sibling repo: visualai-frontend
src/app/
├── modes/
│   └── long-form/
│       └── page.tsx            # NEW — 3-step wizard
├── api/
│   └── long-form-videos/
│       └── route.ts            # NEW — proxy to Layer 2
└── assets/
    └── page.tsx                # EDIT — add Long-Form card variant alongside ProductShoot/Video
```

**Structure Decision**: Three-tier extension. Each layer adds new surfaces only — no refactors to existing routes/components. Mode 3 plugs into spec 015's modes registry skeleton + reuses Mode 1's record-persistence + pre-signed URL pattern.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Demo-tenant in Step-3 (Principle III debt) | Same precedent as Modes 1/2/5 — spec 014 closes the debt for all modes at once | Wrapping Mode 3 alone in tenant plumbing would diverge from the other modes and require throwaway code when spec 014 lands |
| New Layer 2 endpoint instead of routing through `/api/v1/videos` | Mode 3's response shape (LongFormGeneration record + pre-signed URL + per-segment metadata) is meaningfully different from Mode 2's video task shape | Reusing `/api/v1/videos` would require server-side mode-dispatch on the response, which couples wizard-specific UX to a generic endpoint |
| JSON-file store as Step-3 stand-in | Mode 1 (spec 015) already proved the pattern — survives L2 restarts via on-disk record.json + lazy load | An in-memory store was the v1 plan in spec 015 and broke after restarts; we already paid that lesson once |
