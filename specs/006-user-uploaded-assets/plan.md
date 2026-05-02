# Implementation Plan: User-Uploaded Model & Product Assets

**Branch**: `006-user-uploaded-assets` | **Date**: 2026-05-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-user-uploaded-assets/spec.md`

## Summary

Adds a **Visuals** selector to the Creation Wizard's Script & Voice step with two modes: `Auto (stock)` (current Pexels behavior) and `Use my own assets` (user uploads 1 optional model + 1–3 product images). When `Use my own assets` is selected, the rendering pipeline replaces Pexels stock entirely with the user's images, animated via slow zoom + light pan (Ken Burns) and crossfaded between segments. Per Clarifications 2026-05-02, this ships **inside Step 1** mirroring specs 009/010, with a permissive local moderation heuristic gated behind `MODERATION_REQUIRED=False` until a real cloud moderation API lands before public launch.

The branch lives **inside `app/services/material.py.download_videos`** — the function checks `params.visuals_mode == "user_uploaded"` and either calls Pexels (auto, current code) or converts uploaded image paths to per-image clips (new code path). This is the early shape of debt #3's repayment ("rewrite `material.py` to accept pre-signed URLs from Layer 2"). `task.py` is **not** touched — debt #5's line count stays unchanged.

## Technical Context

**Language/Version**: Python 3.11/3.12 (Layer 3); TypeScript / React (Next.js 16 + React 19) on the sibling `visualai-frontend/` Layer 1 repo.
**Primary Dependencies**: MoviePy (already pinned upstream — `ImageClip`, `CompositeVideoClip`, `crossfadein`); Pillow (already a MoviePy transitive dep — used for upload-time validation, EXIF orientation correction, and 9:16 saliency-default crop); FastAPI multipart (already used by spec 009/010's logo + audio upload endpoints); `python-multipart` (transitive). Frontend: native `<input type="file" multiple>` + drag-and-drop (no new dep). **No new runtime dependency.**
**Storage**: Filesystem only.
- Original uploads: `storage/uploads/<uuid>.<ext>` (jpg / png / webp; same dir specs 009/010 use).
- Cropped 9:16 derivatives: `storage/uploads/<uuid>.cropped.jpg` (re-encoded JPEG, sRGB, EXIF stripped).
- Per-task asset audit log: appended to existing `storage/tasks/<task_id>/script.json` under a new `asset_audit` key (matches specs 010/013's "extend task.json" pattern; no new file).
- Generated Ken Burns clips: `storage/tasks/<task_id>/uploaded-<idx>.mp4` (transient — same lifetime as Pexels-downloaded clips).
**Testing**: `pytest test/services/test_uploaded_visuals.py` (offline, MoviePy mocked) + `pytest test/controllers/test_image_upload.py` (FastAPI TestClient). Frontend: Vitest unit tests for `scriptStateToParams`-equivalent helper. Manual quickstart for end-to-end verification.
**Target Platform**: Same as MPT — Python 3.11/3.12 on Linux/Docker; Next.js on Vercel/Node.
**Project Type**: Layer 3 fork (Python service) + Layer 1 client (Next.js, sibling repo).
**Performance Goals**: 10s upload @ 5MB on 20Mbps for 95% of uploads (SC-004); 4 min full generation start-to-playback for 3-product-photo render (SC-002); ≥ 2s screen time per uploaded image in 95% of outputs (SC-007).
**Constraints**:
- 10MB max per image (FR-008), enforced both client-side (pre-upload) and server-side (post-upload, FastAPI middleware).
- Min 720px longest-side soft-warning, accepted (FR-009).
- 9:16 auto-crop, center-default for v1 (FR-011).
- 0 Pexels frames in `user_uploaded` mode (FR-012, SC-001).
- 0 cross-tenant asset visibility (SC-005) — Step 1 single-user means this is trivially met until debt #2 repays.
- `MODERATION_REQUIRED=False` Step-1 default; SC-006 explicitly unmet in Step 1 (Q5 carve-out).
**Scale/Scope**: Step 1 single-user, no concurrent renders. ~5 image uploads per generation max (1 model + up to 3 product + spare slot). Per-tenant scoping deferred to debt #2 burndown in Step 2.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (see end of plan).*

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | **DEBT** | Upload endpoint + local storage live in this Layer 3 repo per Step-1 carve-out (Q1). Mirrors specs 009/010 precedent. **Continues debt #1** (Layer 2 absent); will retire when Step 2 stands up the orchestration tier and uploads route through it. |
| **II. Surgical Fork Discipline** | **PASS** | Touches three fork-surface files: `app/models/schema.py` (new `visuals_mode` + `uploaded_*_paths` fields), `app/services/material.py` (branch inside `download_videos`), `app/controllers/v1/uploads.py` (new image route alongside spec 009's logo + spec 010's audio routes). All three are inside the documented fork-surface set. **No `task.py` edit** — debt #5's line count stays unchanged. **No `video.py` / `voice.py` / `subtitle.py` touch.** |
| **III. Multi-Tenant Context Propagation** | **DEBT** | Step 1 single-user; no `tenant_id` scoping on upload paths. **Continues debt #2** — will retire when Step 2's JWT middleware lands. The `storage/uploads/<uuid>.<ext>` path becomes `storage/uploads/<tenant_id>/<uuid>.<ext>` via the same global path-rewrite that specs 009/010 already inherit. |
| **IV. External Asset Acceptance Over Direct API Calls** | **PASS** (improves) | `Use my own assets` mode calls **zero** external generation/stock APIs — pure user-provided stills. `Auto` mode still uses Pexels (continues debt #3, unchanged). This feature improves Principle IV alignment for Mode 2 specifically. |
| **V. Mode-Aware Rendering Contract** | **PASS** | `visuals_mode` is orthogonal to Agent Mode (1–5) — same shape as spec 013's `script_mode`. The 5 Agent Modes are unchanged. No `app/services/modes/` registry touch needed; field-level dispatch matches spec 013 precedent. **Continues debt #4** to the same extent spec 013 does (no worse). |

**Gate verdict**: PASS-with-tracked-debt. New debt rows (one for the Layer-3 carve-out, one for moderation deferral) are added to STEP1_DEBT.md alongside the existing five.

## Project Structure

### Documentation (this feature)

```text
specs/006-user-uploaded-assets/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── image-upload-endpoint.md       # POST /api/v1/uploads/image contract
│   ├── visuals-mode-wire-shape.md     # VideoParams extension + frontend → backend wire shape
│   ├── material-py-dispatch.md        # Branching rules inside material.download_videos
│   └── wizard-visuals-selector.md     # Layer 1 wizard pill + upload-area UI contract
├── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created here)
├── checklists/
│   └── requirements.md  # /speckit-specify quality checklist (already present)
└── spec.md              # /speckit-specify output (already present, clarified 2026-05-02)
```

### Source Code (repository root)

```text
# Layer 3 (this repo) — touched files only
app/
├── controllers/v1/
│   └── uploads.py                # EXTEND — add POST /api/v1/uploads/image route
├── models/
│   └── schema.py                 # EXTEND — VideoParams gains visuals_mode +
│                                 #          uploaded_model_path + uploaded_product_paths
└── services/
    └── material.py               # EXTEND — download_videos branches on visuals_mode

storage/
├── uploads/                      # NEW LIFETIME — image uploads (alongside spec 009/010 audio + logo)
│   ├── <uuid>.<ext>             # original
│   └── <uuid>.cropped.jpg       # 9:16 center-cropped derivative
└── tasks/<task_id>/
    ├── script.json               # EXTEND — gains `asset_audit` key when visuals_mode=user_uploaded
    └── uploaded-<idx>.mp4        # NEW — per-image Ken Burns clips (transient)

test/
├── controllers/
│   └── test_image_upload.py      # NEW — FastAPI TestClient suite
└── services/
    └── test_uploaded_visuals.py  # NEW — material.py branch + Ken Burns helper unit tests

# Layer 1 (sibling visualai-frontend/ — separate repo, separate PR)
visualai-frontend/
├── src/
│   ├── lib/
│   │   └── visuals-mode.ts       # NEW — type definitions + scriptStateToParams-equivalent helper
│   ├── components/
│   │   └── wizard/
│   │       └── visuals-selector.tsx  # NEW — pill row + upload-slot grid
│   └── app/
│       ├── modes/short-video/
│       │   └── page.tsx          # EXTEND — wire visuals selector into Script & Voice step
│       └── api/
│           ├── generate/route.ts # EXTEND — pass-through new fields to MPT
│           └── upload-image/
│               └── route.ts      # NEW — proxy to MPT POST /api/v1/uploads/image
└── tests/
    └── visuals-mode.test.ts      # NEW — Vitest helper coverage
```

**Structure Decision**: Surgical extension inside the existing fork-surface files. Three Layer-3 files touched (`schema.py`, `material.py`, `uploads.py`); zero new files inside the engine; one new endpoint route inside the existing `uploads.py` module. Layer 1 work is the larger surface (new component + helpers + frontend route) but lives entirely in the sibling repo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Upload endpoint + storage in Layer 3 (Principle I debt) | Layer 2 doesn't exist yet; Cortex41-class B-roll-mismatch problem needs solving now to prove the product. | Waiting for Step 2 = indefinite delay; Pexels-only Mode 2 keeps producing off-topic visuals for any product brand. Specs 009 + 010 set the precedent for this exact carve-out. |
| `MODERATION_REQUIRED=False` Step-1 default (SC-006 unmet) | Wiring a paid cloud moderation API is a separate procurement decision; local heuristics are insufficient for SC-006. | A) Skip moderation: silent SC-006 violation. B) Block on cloud API: stalls Cortex41 fix, requires AWS/Google cloud account decisions. The flag-defaults-to-False approach makes the public-launch upgrade a single config flip and writes the gap as explicit debt. |

Both violations are recorded as new rows in STEP1_DEBT.md alongside debts #1–#5. Repayment paths are concrete (debt #1's path retires the Layer-3 upload carve-out; flipping `MODERATION_REQUIRED=True` retires the moderation carve-out).

## Constitution Re-check (post-Phase 1)

*Re-evaluated after data-model.md + contracts generation.*

- Principle II re-confirmed PASS: final touched-files list is exactly `schema.py` + `material.py` + `uploads.py` (all fork-surface). No drift introduced during contract design.
- Principle V re-confirmed PASS: `visuals_mode` is plain field-level dispatch on `VideoParams`, never reaches into `app/services/modes/` (which doesn't exist yet — debt #4 still tracks that future work).
- No new violations introduced by Phase 1 design.

---

## Hybrid Mode Addition (Clarifications 2026-05-03)

**Why this section exists:** post-implementation testing showed that `visuals_mode = "user_uploaded"` produced slideshow-quality renders for SaaS/product-marketing content. Real product videos cut between *contextual setting* (people, environment) and *product reveal* (UI/screenshot). FR-022..FR-025 add a third `hybrid` mode that interleaves user uploads with Pexels + Pixabay setting footage; `generate_terms` is also tightened to query for industry/setting (not literal product features) so Auto mode benefits too.

### Files affected (additive only)

| File | Touch type | Scope |
|---|---|---|
| `app/models/schema.py` | EXTEND | Add `"hybrid"` to `visuals_mode` Literal; relax `_validate_visuals` so hybrid uses the same product-paths rule as user_uploaded (1–3 required, model optional). |
| `app/services/llm.py` | EXTEND | New `extract_setting_tag(script_text)` returning one of 11 tags; new `expand_setting_to_queries(setting_tag)` returning 5 Pexels-friendly queries; new orchestrator `generate_setting_terms(script_text)` that wraps both. Keeps existing `generate_terms` intact for callers that want literal-product queries. |
| `app/services/material.py` | EXTEND | New `_build_clips_hybrid(task_id, model_path, product_paths, audio_duration, video_aspect, setting_tag)` interleaver. New `_search_stock_dual_source(query, video_aspect, max_clip_duration)` queries Pexels + Pixabay in parallel with dedupe. Two-tier retry helper. `download_videos`'s sidecar branch dispatches on `visuals_mode == "hybrid"` → new helper; existing user_uploaded branch unchanged. |
| `app/controllers/v1/video.py` | EXTEND | `_maybe_write_visuals_sidecar` writes the sidecar when `visuals_mode in ("user_uploaded", "hybrid")`. Sidecar shape gains `visuals_mode: "hybrid"` variant + the resolved `setting_tag` (computed by the orchestrator before dispatch and threaded through). |
| `visualai-frontend/src/lib/visuals-mode.ts` | EXTEND | `VisualsMode` literal grows to `"auto" \| "hybrid" \| "user_uploaded"`. `visualsStateToParams` emits `{visuals_mode: "hybrid", ...}` shape. `canSubmitVisuals` for hybrid mirrors user_uploaded (1–3 products required; model optional). |
| `visualai-frontend/src/app/modes/short-video/page.tsx` | EXTEND | `<VisualsSection>` pill row grows from 2 to 3 options. Helper text updated per mode. |
| `visualai-frontend/src/app/api/generate/route.ts` | EXTEND | Pass-through accepts `visuals_mode === "hybrid"` alongside the existing two values. |

### Constitution check delta

- **Principle II** still PASS: same fork-surface set as before (schema.py + llm.py + material.py + uploads.py + video.py controller).
- **Principle IV** still improved (hybrid mode calls Pexels + Pixabay, both already inherited from upstream MPT — no new external generation API). The two-pass setting-tag prompt is an LLM call routed through the existing `_generate_response` path, no new provider.
- **Debt #4 unchanged**: hybrid mode's setting-tag + query-expansion prompts live inline in `llm.py` alongside the Mode 2 marketing-script prompt and spec 013's polish prompt. They all repay together when Step 3's mode registry lands.
- **Debt #5 unchanged**: zero new `task.py` edits — the sidecar pattern keeps `download_videos`'s call signature stable.

No new debt introduced.

### Performance budget

- Two-pass LLM round-trip for setting-tag + queries: ~2× a single `generate_terms` call. Acceptable given Mode 2 already runs an LLM call for script generation; one extra short prompt is < 5% total render time.
- Pexels + Pixabay in parallel: same wall-clock as a single source (parallelized via `concurrent.futures` or sequential since per-request latency is < 1s).
- Setting-tag cache: deferred to Step 3+ (per-tenant cache on the resolved setting given the script text would save the round-trip on iterative renders, but Step 1 doesn't have a tenant scope yet).
