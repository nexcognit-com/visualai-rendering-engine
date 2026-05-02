# Implementation Plan: Static Brand Overlays on Rendered Videos

**Branch**: `009-brand-overlays` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/009-brand-overlays/spec.md`

## Summary

Add a second-pass MoviePy compositor to MoneyPrinterTurbo that overlays a user-supplied logo PNG and/or a static rectangle on top of the rendered video. The compositor lives in a new VisualAI-only file (`app/services/overlays.py`) so the upstream `app/services/video.py` stays rebase-clean per Principle II. Overlays are described by a `List[Overlay]` field on `VideoParams`; logos are uploaded via a new `POST /api/v1/uploads/logo` endpoint that stores files at `storage/uploads/<uuid>.<ext>`. The frontend wizard's Step 3 grows an "Overlays" panel with a logo upload + corner picker and a rectangle config (corner, size preset, color, opacity). When `params.overlays` is empty the pipeline behaves byte-identical to today (zero regression). All existing MoviePy primitives the compositor needs (`CompositeVideoClip`, `ImageClip`, `ColorClip`) are already imported in `video.py:12-15`, so no new runtime dependency.

## Technical Context

**Language/Version**: Python 3.11/3.12 (matches constitution); TypeScript / React on the frontend (Next.js 16 + React 19, already in `visualai-frontend/`)
**Primary Dependencies**: MoviePy (already pinned in upstream `requirements.txt`), Pillow (already a MoviePy dependency), Fastify-style multipart in MPT's existing FastAPI controllers (`python-multipart` already in upstream deps), Next.js `Form` + browser FormData on the client side. **No new runtime dependency.**
**Storage**: Filesystem at `storage/uploads/<uuid>.<ext>` for uploaded logos; existing `storage/tasks/<task_id>/` continues to hold render artifacts. Original `final-N.mp4` preserved for debugging; overlay-applied output named `final-overlaid-N.mp4` and surfaced as the user-facing path in `/api/history`.
**Testing**: pytest smoke covering the compositor with synthetic PNG + synthetic stub video (1s ColorClip + uploaded logo composite); manual end-to-end via the wizard. Per the constitution, "new mode code requires at least one smoke test exercising the rendering path with mocked Layer 2 inputs" — overlays count as render-pipeline code so a smoke test ships.
**Target Platform**: GPU-capable host for production (per constitution); CPU-only is fine for the overlay second-pass (composite is cheap relative to the upstream stitch).
**Project Type**: Layer 3 rendering-engine feature with a Layer 1 wizard surface — both layers in scope.
**Performance Goals**: Overlay second-pass ≤ 30% of original render time on a 30 s 9:16 video (SC-003). On a typical Mode 2 render (~80 s today), expect the overlay step to add ≤ 24 s.
**Constraints**: MUST NOT modify `app/services/video.py` (Principle II: keep upstream MoviePy assembly code rebase-clean). MUST NOT silently fall back to overlay-less output on compositor failure (FR-013). MUST be byte-identical to today when `params.overlays` is empty (SC-002).
**Scale/Scope**: ≤ 5 overlays per render (FR-010), ≤ 5 MB per logo upload (FR-002), per-render uploads only at v1 (no Brand Library yet). Single-tenant single-user storage layout shares `storage/uploads/`; tenant-scoping arrives in Step 2 of the build plan via debt #2 burndown.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.2 governs this Layer 3 repo. Spec 009 spans Layer 1 (wizard UI) and Layer 3 (overlay compositor + upload endpoint). The principles are evaluated below.

| Principle | Verdict | Reasoning |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | PASS | The Layer 3 portion is exactly rendering work — composite a logo onto an MP4. The Layer 1 wizard adds the UI for picking overlays; that's Layer 1's job by design. No user/credit/billing logic enters this repo. |
| **II. Surgical Fork Discipline** | PASS, with continuation of existing debts | Touches **fork-surface files**: `app/models/schema.py` (already touched in Step 1) for the new `Overlay` Pydantic model + `overlays` field on `VideoParams`; `app/controllers/v1/uploads.py` is a **new controller file** under the fork-surface controllers directory. **Does NOT touch** `app/services/video.py` (the core MoviePy stitcher) — the second-pass compositor lives in a NEW VisualAI-only file `app/services/overlays.py`. **Touches `app/services/task.py`** for one more line (the overlay step call) — `task.py` is already tracked as STEP1_DEBT.md row #5; this feature adds a second touch line, repaid together at Step 3. |
| **III. Multi-Tenant Context Propagation** | PASS, via existing debt | Step 1 ships single-user; uploads land in shared `storage/uploads/` without tenant scoping. This is a continuation of debt #2 (no `tenant_id` on requests). When debt #2 repays in Step 2 (JWT middleware), uploads scope per-tenant. No new debt. |
| **IV. External Asset Acceptance Over Direct API Calls** | PASS | No external APIs. Overlays come from user uploads (filesystem) at v1; in v2 they'll come from Brand Library assets (still tenant-scoped storage, not API calls). |
| **V. Mode-Aware Rendering Contract** | PASS, via existing debt | Overlays are wired into Mode 2 directly via the wizard, not via the (yet-to-exist) `app/services/modes/` registry. Continuation of debt #4 (mode prompts inline in `llm.py`). When the registry lands at Step 3, overlay-mode-applicability moves into the registry alongside the existing prompt dispatch. No new debt. |
| **§Technology Constraints — Runtime** | PASS | Python 3.11/3.12; uses MoviePy + Pillow already pinned. No new dependency. |
| **§Technology Constraints — Database** | N/A | No PostgreSQL, no Redis, no DDL. Filesystem only. |
| **§Technology Constraints — Observability** | PASS | The overlay step uses loguru (matches existing MPT logging discipline). Each composite log line includes `task_id` so failures are traceable. |
| **§Technology Constraints — Secrets** | PASS | No API keys. |
| **§Development Workflow — fork-surface PR rule** | APPLIES | This PR touches fork-surface `app/models/schema.py` and `app/controllers/v1/uploads.py` (new). Per the constitution, "PRs touching the five fork-surface files MUST reference the affected Agent Mode(s) and cite the relevant Master Spec section in the PR body." The implementation PR for this spec MUST cite Mode 2 (Short Marketing Video) and Master Spec §3 (Five Agent Modes). |
| **§Development Workflow — pytest gate** | APPLIES | At least one smoke test exercising the overlay render path with a synthetic PNG + stub video MUST exist before this feature merges. |

**Gate result**: PASS. No NEW constitutional violations to justify. Three existing debts (#2, #4, #5) gain one more burndown task each (already noted in spec's §Constitutional Impact). Re-check post-Phase 1.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/009-brand-overlays/
├── plan.md                    # This file
├── research.md                # Phase 0 — MoviePy compositor patterns, upload endpoint approach, frontend Form patterns
├── data-model.md              # Phase 1 — Overlay Pydantic model, Logo Asset, Composite Pass entities + validation rules
├── quickstart.md              # Phase 1 — operator runbook (apply overlay locally; verify SC-001 and SC-002)
├── contracts/
│   ├── overlay-schema.md            # Pydantic schema for Overlay (logo + rectangle discriminated union)
│   ├── upload-endpoint.md           # POST /api/v1/uploads/logo HTTP contract
│   └── compositor-contract.md       # apply_overlays() function contract — input/output, error semantics
├── checklists/
│   └── requirements.md        # Spec quality checklist (already created)
├── spec.md                    # Feature specification
└── tasks.md                   # Phase 2 — produced by /speckit.tasks (NOT here)
```

### Source code changes (Layer 3 — this repo)

```text
app/
├── models/
│   └── schema.py                    # MODIFIED: add Overlay model + overlays field on VideoParams
├── controllers/v1/
│   └── uploads.py                   # NEW: POST /api/v1/uploads/logo multipart endpoint
└── services/
    ├── overlays.py                  # NEW: apply_overlays(input_mp4, overlays) → str — second-pass MoviePy compositor (VisualAI-only addition; NOT a fork-surface file)
    ├── task.py                      # MODIFIED: 1 new line invoking apply_overlays() after combine_videos() (already tracked as debt #5)
    └── video.py                     # UNTOUCHED — Principle II: upstream MoviePy assembly code stays rebase-clean
storage/
└── uploads/<uuid>.<ext>             # NEW directory — per-render logo uploads
test/
└── services/
    └── test_overlays.py             # NEW: smoke test exercising apply_overlays() with synthetic PNG + ColorClip stub
```

### Source code changes (Layer 1 — `visualai-frontend/`)

```text
visualai-frontend/src/
└── app/
    ├── modes/short-video/
    │   └── page.tsx                 # MODIFIED: append "Overlays" panel to Step 3 — logo upload + corner picker + rectangle config
    └── api/
        ├── generate/route.ts        # MODIFIED: pass overlays through to MPT (already passes mode + concat_mode + transition_mode)
        └── upload-logo/
            └── route.ts             # NEW: multipart proxy to MPT's /api/v1/uploads/logo (keeps bearer-secret-free contract; mirrors how /api/generate proxies)
```

**Structure Decision**: Layer 1 changes localize to the wizard page and a new API proxy route. Layer 3 changes localize to one new file (`overlays.py`), one new controller (`uploads.py`), and a one-line wiring edit in `task.py`. The upstream `video.py` is left untouched, satisfying Principle II's rebase-clean requirement. The `storage/uploads/` directory is a new, gitignored, runtime-only filesystem location — it's not a code change, just a runtime convention.

## Complexity Tracking

> No NEW Constitution violations. Section minimal.

This feature deliberately rejects four heavier alternatives:

- **Drag-and-drop pixel positioning UI** — rejected: requires a real video preview component in the wizard. Corner pickers + size presets cover the actual job. Drag-positioning lands as a v2 polish if user feedback demands it.
- **Per-frame face/object detection (real CV)** — rejected: this was the user's initial framing; clarified to "I just want to draw a box / add a logo" in the 2026-05-02 session. CV is a fundamentally different feature and would justify its own mode + spec.
- **Storing uploads in cloud (R2/S3) at v1** — rejected: Step 1 is local-filesystem-everything; cloud storage arrives in Step 4 alongside the Neon DB and Layer 4 work. The `Overlay.source_path` field accepts any path string today, so the migration to cloud storage doesn't break the schema.
- **Driving overlays via natural-language LLM parsing** — rejected per User Story choice: structured UI is deterministic and predictable; NL parsing is sugar that can layer on top later (see Spec § Open Follow-ups in research.md).
