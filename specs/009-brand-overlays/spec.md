# Feature Specification: Static Brand Overlays on Rendered Videos

**Feature Branch**: `009-brand-overlays`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "Static overlays: logo + rectangle on Mode 2 renders, with hooks for future Brand Library integration"

## Overview

Add a way for VisualAI users to attach static visual overlays — a logo image, or a hard-coded rectangle — to a rendered video, so the final MP4 carries the user's brand mark or a deliberate visual annotation. The overlay is composited server-side as a second MoviePy pass after the existing pipeline produces the stitched video; no computer vision, no per-frame analysis, no detection — just a deterministic composite over every frame.

This feature was discovered as a real friction point during Mode 2 testing: a user typed an instruction like "put a logo in the corner" into the wizard's script editor, the LLM treated it as marketing-copy context, and the rendering pipeline produced a polished ad that silently ignored the request because there is no `Overlay` field on `VideoParams` and no overlay step in the render pipeline. The gap is small (the underlying MoviePy stitcher already supports composites) but the user-facing impact is large (the agent appears to ignore explicit instructions). This spec closes that gap by adding a structured wizard panel that produces typed overlay records the pipeline can act on.

The overlay model is **forward-compatible** with the future Brand Library feature anticipated in Step 5 of the build plan. v1 ships per-render overlays (upload a logo each render); when the Brand Library lands, the wizard pre-populates the logo source from the tenant's saved assets without changing the `Overlay` data shape.

## Clarifications

### Session 2026-05-02

- Q: Should this spec also cover music tracks (BGM)? → A: No. Music is out of scope for 009. The MPT backend already supports BGM (`bgm_type`/`bgm_file`/`bgm_volume` on `VideoParams`, 29 BGM files in `resource/songs/`, mixing happens at `app/services/video.py:545-550`), but the wizard exposes no music UI today. Music control gets its own feature 010 — separate spec, parallel-deliverable, no shared files with this spec. Spec 009's scope contraction to "visual overlays only" is reaffirmed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — User adds a logo to their Mode 2 ad (Priority: P1)

A creator finishes the wizard's script + voice + music selections and, before clicking generate, opens an Overlays panel in the same step. They upload a transparent PNG of their logo, pick "bottom-right" as the position, leave the size and opacity defaults alone, and submit. The final 9:16 MP4 has their logo composited cleanly into the bottom-right corner of every frame, sized at ~15% of the video width with a comfortable margin from the corner.

**Why this priority**: this is the entire reason the feature exists. A marketer producing brand-tagged short videos cannot do their job if the video doesn't carry their brand. Without P1, every Mode 2 render goes out unbranded.

**Independent Test**: Generate two Mode 2 videos for the same subject — one with no overlay, one with a logo overlay — and visually inspect both. The first MUST match today's pipeline output exactly. The second MUST have the logo crisply composited in the picked corner of every frame, with the rest of the video identical to the first.

**Acceptance Scenarios**:

1. **Given** the wizard's Step 3 is open with a logo PNG uploaded and "bottom-right" picked, **When** the user submits the wizard, **Then** the final MP4 has the logo composited in the bottom-right corner with default size (~15% of video width) and default margin (~24 px), preserving the PNG's alpha channel.
2. **Given** a logo is uploaded with opacity set to 50%, **When** the wizard submits, **Then** the rendered logo is half-transparent over the video.
3. **Given** the wizard is opened and no overlay is configured, **When** submitting normally, **Then** the rendered video is byte-identical to a render with no overlay system at all (zero regression).
4. **Given** a logo upload fails (file too large, wrong format), **When** the user attempts to submit, **Then** the wizard surfaces a typed error before sending the render request — the render does NOT start with a corrupt/missing logo reference.

---

### User Story 2 — User adds a static rectangle to highlight a region (Priority: P2)

A user wants to draw attention to a visual element in their video — for example, a "NEW" callout box or a brand-colored highlight bar at the bottom of frame for promo copy. They open the Overlays panel, pick "rectangle" as the kind, choose a corner + size preset (small / medium / large), pick a color and opacity, and submit. The rendered MP4 has that rectangle composited on top of every frame.

**Why this priority**: lower-frequency use case than logos but the same data model + same pipeline path with one extra `kind` value. Cheap to support if logo support is built. Skipping it would force users to mock rectangles in third-party editors when the feature otherwise exists.

**Independent Test**: Generate a Mode 2 video with a single rectangle overlay (e.g., bottom-center, medium size, brand-accent color, 60% opacity). The final MP4 MUST show that rectangle in every frame at the specified position, color, and opacity.

**Acceptance Scenarios**:

1. **Given** the user picks rectangle kind + corner-bottom-center + size-medium + color brand-accent + opacity 60%, **When** they submit, **Then** the final MP4 has a brand-accent rectangle of the medium preset size at bottom-center with 60% opacity, on every frame.
2. **Given** the rectangle would extend past the video bounds (selected size > available space), **When** the wizard validates, **Then** the wizard either clamps the size to the video bounds or surfaces a "rectangle would clip" warning before render.

---

### User Story 3 — User stacks multiple overlays in one render (Priority: P3)

A power-user wants both a logo (top-left) and a brand-colored highlight bar (bottom). The wizard accepts both, the API model carries them as a list, and the rendered MP4 has both composited cleanly with consistent z-order (later overlays render on top).

**Why this priority**: power-user case. The data model needs to be a list either way (a single overlay is just a list of length 1), so supporting N overlays is "free" in terms of schema. The wizard UX is the only extra cost — needs an "add another overlay" button or similar.

**Independent Test**: Configure a logo + a rectangle in the same wizard submission. The rendered MP4 MUST contain BOTH overlays in their picked positions; neither MUST occlude the other in unexpected ways.

**Acceptance Scenarios**:

1. **Given** the user configures one logo (top-left) and one rectangle (bottom-center), **When** the render completes, **Then** both overlays appear in the final MP4 at their picked positions.
2. **Given** the user configures two overlays that would visually collide (e.g., two logos at the same corner), **When** the wizard validates, **Then** it warns about overlap before submitting.

---

### User Story 4 — Brand Library forward-compatibility hook (Priority: P3, deferred implementation)

When the Brand Library feature lands (Step 5 of the build plan), a tenant's saved logo can be selected from a dropdown rather than uploaded fresh each render. The Overlay data shape MUST accommodate a `source_path` that points either to a per-render upload (today) or to a Brand Library asset (future). v1 implements only the per-render upload path; the spec ensures v2 can extend without a schema break.

**Why this priority**: not a v1 user-visible feature, but worth specifying because the schema choice today determines whether v2 requires a migration. Cheap to get right now, expensive later.

**Independent Test**: review the `Overlay.source_path` field in the v1 schema against the Brand Library design intent in the 5-step plan; confirm a future Brand Library asset (which will live at a deterministic path like `brand-library/<tenant>/<asset-id>.png`) can be referenced through the same field with no schema change.

---

### Edge Cases

- **Logo too large**: A user uploads a 50 MB PNG. The upload endpoint rejects above a size cap (suggested 5 MB) before storage. Wizard surfaces the rejection clearly.
- **Logo wrong format**: A user uploads a JPG, BMP, or non-image file. The upload endpoint rejects anything not PNG, JPG, or WebP. (PNG is preferred for alpha.)
- **Logo with no transparency**: A user uploads an opaque PNG/JPG. The composite still works but the logo's bounding rectangle covers part of the video. Wizard MAY warn that "this image has no transparency — it will appear as a solid rectangle"; not required at v1.
- **Rectangle outside video bounds**: User picks size-large at corner-bottom-right with a margin that would clip. Wizard clamps to fit, OR surfaces "rectangle clipped".
- **Overlay applied to a failed render**: Render fails mid-pipeline (Pexels timeout, FFmpeg crash) before the overlay step. The overlay is never composited because there's no input video. Wizard surfaces the underlying render failure normally; overlay state isn't lost (the user's overlay config is preserved in the wizard for retry).
- **Render succeeds but overlay step fails**: MoviePy can't open the uploaded logo (corrupt PNG that passed upload validation). The pipeline either produces the overlay-less video and warns, or fails the whole render with a typed error. v1 chooses the latter (fail clearly) to avoid silently degrading user intent.
- **Multiple overlays at the same corner**: Two logos both pinned to top-left would visually collide. Wizard warns OR auto-offsets the second by the size of the first. v1: warn, don't auto-offset (deterministic > clever).
- **No overlays configured**: The render pipeline behaves identically to today — overlay step is skipped entirely if `params.overlays` is empty. Zero regression.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: VisualAI Mode 2 wizard MUST expose an "Overlays" UI panel inside Step 3 of the wizard (alongside the existing voice and music selectors). The panel MUST be optional — a wizard with no configured overlays MUST behave identically to today.
- **FR-002**: The Overlays panel MUST support adding a **logo overlay** with: (a) PNG/JPG/WebP upload up to 5 MB, (b) position picker (top-left, top-right, bottom-left, bottom-right, center), (c) size as a percentage of video width (default 15%, range 5%–40%), (d) opacity (default 100%, range 10%–100%), and (e) a configurable corner margin (default 24 px).
- **FR-003**: The Overlays panel MUST support adding a **rectangle overlay** with: (a) position picker (same five values as logo), (b) size preset (small / medium / large) or explicit pixel dimensions, (c) color picker (hex input + a small preset palette including the brand accent token from spec 001), (d) opacity (default 50%, range 10%–100%).
- **FR-004**: The Overlays panel MUST support **multiple overlays per render**. The wizard MUST emit them as an ordered list; the render pipeline MUST composite them in list order (later overlays on top).
- **FR-005**: `VideoParams` (in `app/models/schema.py` — fork-surface) MUST gain an `overlays: List[Overlay] = []` field. The `Overlay` Pydantic model MUST capture all logo + rectangle fields in a single discriminated-union shape so future overlay kinds (text, GIF, animated logo) can extend without breaking changes.
- **FR-006**: A new render-engine module `app/services/overlays.py` (NOT in the upstream MPT fork-surface) MUST implement `apply_overlays(input_mp4: str, overlays: List[Overlay]) -> str`. It MUST use MoviePy's `CompositeVideoClip` to composite each overlay onto the existing rendered MP4 and write a new MP4 path (preserving the original input as an artifact). It MUST NOT modify the upstream `app/services/video.py` (which is core MoviePy assembly code per Principle II — kept upstream-compatible).
- **FR-007**: `app/services/task.py` MUST invoke `apply_overlays()` immediately after `combine_videos()` produces the stitched MP4, ONLY when `params.overlays` is non-empty. When `params.overlays` is empty, the call MUST be skipped entirely (no MoviePy second pass, no perf impact).
- **FR-008**: A new endpoint `POST /api/v1/uploads/logo` (in `app/controllers/v1/`, fork-surface) MUST accept a multipart upload, validate format (PNG/JPG/WebP) and size (≤ 5 MB), save the file to `storage/uploads/<uuid>.png` (or appropriate extension), and return a JSON `{path: "storage/uploads/<uuid>.png"}`. The path returned is what the wizard places into the `Overlay.source_path` field on the subsequent generate request.
- **FR-009**: The frontend MUST proxy logo uploads through a `POST /api/upload-logo` route to keep the bearer-secret-free contract; the proxy multiparts to MPT's `/api/v1/uploads/logo` and returns the path.
- **FR-010**: The wizard MUST validate locally before submission: file format, file size, opacity range, size ranges, color hex format, count of overlays (≤ 5). Validation failures MUST surface inline before render starts.
- **FR-011**: When `params.overlays` is populated, the rendered output MUST be a new MP4 file with the overlays composited; the original `final-N.mp4` MAY be preserved as an artifact for debugging but the path returned to the frontend (and surfaced in My Assets) MUST be the overlay-applied version.
- **FR-012**: The `Overlay.source_path` field MUST be schema-compatible with future Brand Library assets — the field MUST accept any path string the engine can resolve, whether it points to `storage/uploads/<uuid>.png` (today) or to a Brand Library asset path (future v2).
- **FR-013**: All overlay-rendering errors (corrupt PNG, MoviePy compositor failure) MUST surface as typed, user-facing errors. The pipeline MUST NOT silently skip the overlay step and return an unmarked video.

### Key Entities

- **Overlay** (Pydantic discriminated union by `kind`):
  - `kind: Literal["logo", "rectangle"]`
  - `position: Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]`
  - `opacity: float` (0.1–1.0; default 1.0 for logo, 0.5 for rectangle)
  - `margin_px: int` (default 24)
  - **logo-only fields**: `source_path: str` (returned by upload endpoint), `width_pct: float` (0.05–0.40, default 0.15)
  - **rectangle-only fields**: `color: str` (hex), `size_preset: Literal["small", "medium", "large"] | None`, `width_px: int | None`, `height_px: int | None` (preset OR explicit, not both)
- **Logo Asset**: a PNG/JPG/WebP file uploaded to `storage/uploads/<uuid>.<ext>`. v1 is per-render — the file persists with the render artifacts. v2 (Brand Library) will move to `brand-library/<tenant>/<asset-id>.<ext>` with the same path-string contract.
- **Composite Pass**: the second MoviePy pass that takes `final-N.mp4` + the list of overlays and produces `final-overlaid-N.mp4`. Stateless — overlays in, MP4 out.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user-uploaded logo overlay (default settings) on a typical 30 s Mode 2 render produces a final MP4 with the logo visibly and crisply composited in every frame, in the chosen corner. Verified by frame-spot-checks in 3 sampled renders.
- **SC-002**: When the wizard's overlay panel is left empty, the rendered output is byte-identical (or render-time-identical within a 5% tolerance) to a render produced from a wizard with NO overlay UI at all. Confirms zero regression on the existing happy path.
- **SC-003**: Adding a single overlay adds ≤ 30% to total render time on a 30 s 9:16 video. Verified by timing matched-pair renders (with vs without overlay) on the same hardware.
- **SC-004**: 100% of overlay-step failures (corrupt PNG, MoviePy crash) surface as typed errors visible in the wizard's progress UI and logs — zero silent fallbacks to overlay-less output.
- **SC-005**: The frontend's overlay panel takes ≤ 60 seconds for a first-time user to discover, configure (logo upload + corner pick), and submit, on a representative test of 3 unfamiliar users. Measured by wall-clock from "Step 3 first opens" to "submit clicked."
- **SC-006**: Schema forward-compatibility test: a synthetic `Overlay` payload with `source_path: "brand-library/tenant_abc/logo_v2.png"` (a future Brand Library path that doesn't exist yet) MUST validate against the v1 Pydantic model. Confirms FR-012 won't bite later.

## Assumptions

- **MoviePy + Pillow are already present in the project's runtime environment.** Both are already used by the existing pipeline (`app/services/video.py`, `app/services/material.py`); no new dependency installation is required.
- **The pipeline produces a deterministic `final-N.mp4` per task** (already true in MPT's storage layout). The composite pass slots in cleanly after this artifact exists.
- **Storage layout for uploads is local filesystem** at `storage/uploads/`. v1 doesn't deal with cloud storage (R2 / S3 etc.); when the project moves uploads to durable storage in Step 4, the `source_path` field absorbs that change without a schema migration.
- **Per-render uploads are acceptable for v1.** A user re-uploads their logo every render rather than picking from a saved library. The Brand Library feature in Step 5 will replace this, but tonight's friction is "the agent ignores my logo request" — that's solved by per-render uploads.
- **No multi-tenant isolation at v1.** Step 1 of the build plan is single-user/no-auth; uploads land in a shared `storage/uploads/` dir. When tenant context arrives in Step 2, uploads scope to `storage/uploads/<tenant_id>/<uuid>.<ext>`. The `source_path` field absorbs that without schema change.
- **Maximum 5 overlays per render** to bound the second-pass render time. Practical cap; no creator should need more for short ads.
- **Mode 2 is the only consumer at v1.** The Overlay model is mode-agnostic — Modes 1, 3, 4, 5 can opt into overlays as they ship without schema changes — but tonight only the Mode 2 wizard exposes the panel.
- **Audio is out of scope.** This spec is strictly visual overlays. Music / BGM control is tracked separately in feature 010 (to be specified). The wizard's "Overlays" panel introduced here MUST NOT include any audio-track UI, even though MPT's `VideoParams` already carries `bgm_*` fields — those fields stay defaulted from this spec's perspective and are owned by feature 010's wizard surface.
- **Wizard validation is client-side first**, with server-side validation as a backstop. Faster feedback for the user; defense-in-depth for correctness.

## Dependencies

- This feature touches three fork-surface files (`app/models/schema.py`, `app/controllers/v1/uploads.py` (new), `app/services/task.py`) and adds one new file outside the fork-surface (`app/services/overlays.py`).
- `task.py` is already tracked as Step 1 debt #5 in `STEP1_DEBT.md`. This feature adds one more line to the same `task.py` debt — flagged below in the Constitutional Impact section.

## Constitutional Impact

| Principle | Impact | Mitigation |
|---|---|---|
| **I. Layer 3 Scope** | None — this is render-engine functionality, exactly Layer 3's job. | n/a |
| **II. Surgical Fork Discipline** | `app/services/task.py` gets one more one-line edit (the `apply_overlays()` call). It's already tracked as debt #5. The edit is small and continues debt #5's existing repayment plan (Step 3 mode registry will absorb both task.py edits cleanly). | Note in STEP1_DEBT.md row #5 that this feature adds the second `task.py` line; both lines repay together at Step 3. |
| **III. Multi-Tenant Context** | Uploads at v1 land in a shared dir without tenant scoping (debt #2 already covers this gap). When debt #2 repays (Step 2 JWT middleware), uploads will scope per-tenant. | No new debt; piggybacks on existing #2. |
| **IV. External Asset Acceptance** | None — overlays come from user uploads, not external APIs. v1 is local filesystem; v2 with Brand Library is still tenant-scoped storage, not direct API calls. | n/a |
| **V. Mode-Aware Rendering Contract** | Overlays are wired into Mode 2 directly via the wizard, not via the (yet-to-exist) `app/services/modes/` registry. Step 3 will move overlay-mode-applicability into the registry alongside the existing mode-dispatch debt #4. | No new debt; piggybacks on existing #4. |

**Net constitutional impact**: zero new debts, two existing debts (#2 and #4) gain one more burndown task, and debt #5 gains a second touch line — all of which repay cleanly when their scheduled repayment steps arrive.

## Cross-references

- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md) — Step 5 anticipates "Brand library with visual memory (persisted product assets)"; this feature's `Overlay.source_path` is the schema hook for that.
- [Constitution v1.0.2](.specify/memory/constitution.md) — Principle II (fork-surface), Principle V (mode-aware rendering); see Constitutional Impact table above.
- [Spec 001 — UI Style](../001-nexcognit-ui-style/spec.md) — the rectangle overlay's color preset palette pulls from spec 001's documented brand tokens (FR-001 of spec 001).
- [Spec 002 — Video Duration / Variations / Preview Gate](../002-video-duration-variations/spec.md) — when preview-gate ships, overlays SHOULD also be applied to preview renders so the preview reflects the user's actual choices.
- [STEP1_DEBT.md](../../STEP1_DEBT.md) — debt #5 (task.py edits) gains one more touch line via this feature; debts #2 and #4 gain one more burndown task each.
