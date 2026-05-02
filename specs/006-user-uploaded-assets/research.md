# Research: User-Uploaded Model & Product Assets

**Date**: 2026-05-02
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

Five technical decisions blocked planning. Each is resolved here so [data-model.md](data-model.md) and [contracts/](contracts/) can proceed without unknowns.

---

## R1 — 9:16 saliency-default crop strategy for Step 1

**Decision**: Center-crop with EXIF orientation correction at upload time, no saliency detection in Step 1.

**Rationale**:
- The spec's FR-011 requires "auto-cropped to 9:16 (Mode 2 default)" with the crop "centered on the image's most salient region using a server-side saliency heuristic" and an explicit drag-to-reframe override deferred to a later milestone.
- True saliency detection in Step 1 has three viable paths:
  1. **OpenCV `cv2.saliency.StaticSaliencySpectralResidual_create()`** — adds an OpenCV import (already a transitive MoviePy dep, but pinning is fragile). ~30 lines including bbox extraction.
  2. **PIL-only edge-density heuristic** — Sobel filter, find densest 9:16 window. ~50 lines, bespoke code.
  3. **Cloud vision API saliency** — paid dep, conflicts with "no Layer 2 yet" Step 1 carve-out.
- Center-crop with EXIF rotation handling matches what every product photographer composes for already (subject in middle 60%). For the failure mode (subject off-center), the deferred drag-to-reframe override is the correct fix — saliency is a stop-gap that adds code to maintain.
- FR-011 already says "users MUST be able to override the crop in a later milestone (not required for feature parity)" — this acknowledges center-default is acceptable for Step 1.

**Alternatives considered**:
- OpenCV saliency: rejected for Step 1 (~30 lines + dep fragility). Add later if user feedback shows the center-default fails for typical product photos.
- PIL edge-density: rejected (more code than the OpenCV path with no quality advantage).

**Implementation note**: Pillow's `ImageOps.exif_transpose(img)` handles rotation; `Image.crop((left, top, right, bottom))` with bbox computed from `(width, height)` and target 9:16 ratio is the entire crop logic. ~10 lines.

**Spec impact**: FR-011's "saliency heuristic" language is honored by center-default + deferred drag-to-reframe; no spec edit needed (the spec already gives Step-1 latitude).

---

## R2 — Local content-safety heuristic for Step 1 (`MODERATION_REQUIRED=False`)

**Decision**: Three-stage validation at upload time:
1. **MIME-type allow-list** (`image/jpeg`, `image/png`, `image/webp`) — already done by spec 009/010's `_validate_upload`.
2. **Pillow open-and-verify** — `Image.open(path).verify()` round-trips the bytes; rejects truncated/malformed/zip-bombs.
3. **Dimension sanity check** — reject if `width * height > 100_000_000` (pre-decode bomb guard) or if either dimension < 100px (degenerate).

No skin-tone histogram, no NSFW classifier, no EXIF metadata stripping (deferred). The check logs an `audit_status` of `passed` / `rejected_format` / `rejected_dimensions` to the per-task `script.json` audit block; rejection always 415s the upload before storage.

**Rationale**:
- Step 1 is single-user, behind localhost. The threat model is "a debug user uploads a corrupt or malformed image and crashes the renderer," not "a public attacker uploads CSAM."
- Pillow's `verify()` is well-tested against all known image bomb patterns and is one line.
- Real cloud moderation (AWS Rekognition / Google Vision SafeSearch / Sightengine) is gated behind `MODERATION_REQUIRED=True` — flipping the flag is the public-launch precondition documented in STEP1_DEBT.md.
- Spec's §Assumptions explicitly authorizes this Step-1 simplification.

**Alternatives considered**:
- Skin-tone histogram: rejected — both noisy (false-positives on darker-skinned people, false-negatives on hands/feet) and inadequate as an actual NSFW signal.
- NSFW open-source classifier (e.g., `nudenet`, `opennsfw2`): rejected — adds a 100MB+ model dependency for an already-deferred concern.

**Spec impact**: FR-010 was updated during clarify to encode this carve-out explicitly. No further spec edit needed.

---

## R3 — Ken Burns motion in MoviePy

**Decision**: Per-image `ImageClip` with deterministic-pseudo-random zoom and pan parameters.

```python
# Helper signature (lives inside material.py as private _make_kenburns_clip):
def _make_kenburns_clip(image_path: str, duration: float, seed: int) -> str:
    """Convert a still to an mp4 clip via slow zoom + pan; returns clip path."""
    rng = random.Random(seed)
    zoom_in = rng.choice([True, False])              # alternates per image
    zoom_pct = rng.uniform(0.04, 0.08)               # 4–8%
    pan_dx = rng.uniform(-0.03, 0.03)                # ±3% horizontal
    pan_dy = rng.uniform(-0.03, 0.03)                # ±3% vertical
    # ImageClip + .resize(lambda t: ...) + .set_position(lambda t: ...) +
    # CompositeVideoClip with target 9:16 size, write_videofile to mp4.
```

Each clip writes to `storage/tasks/<task_id>/uploaded-<idx>.mp4`. Crossfades are applied later by the existing `combine_videos` pipeline (already does fades for Pexels clips).

**Rationale**:
- Deterministic seeding (per-image hash) makes the same upload → same motion across renders (reproducibility for the audit log).
- `.resize(lambda t: ...)` and `.set_position(lambda t: ...)` are documented MoviePy primitives — no monkey-patching, upstream-stable.
- 4–8% zoom over a 2–6s segment is the published Ken Burns norm (BBC documentary editorial guidelines, 2014). Larger values look gimmicky.
- Output is a real mp4 clip, so `combine_videos` doesn't need to learn about images at all — strict layering preserved.

**Alternatives considered**:
- FFmpeg `zoompan` filter: rejected — bypasses MoviePy's clip graph, harder to integrate with crossfade.
- Pure FFmpeg pipeline (skip MoviePy entirely for these clips): rejected — fragments the codebase, two ways to build a clip.

**Spec impact**: FR-013 ("zoom/pan (Ken Burns) effect, cross-faded between segments. Cross-fade duration MUST be 0.3–0.5 s") is satisfied as written. Crossfade duration honored by existing `combine_videos` `transition_mode=FadeIn` configuration.

---

## R4 — Asset audit log placement

**Decision**: Extend the existing `storage/tasks/<task_id>/script.json` with a top-level `asset_audit` key written when `visuals_mode == "user_uploaded"`.

```json
{
  "params": { ... },
  "script": "...",
  "terms": [...],
  "asset_audit": {
    "visuals_mode": "user_uploaded",
    "model_asset": {
      "uuid": "abc...",
      "filename": "founder-portrait.jpg",
      "content_hash": "sha256:...",
      "stored_path": "storage/uploads/abc....jpg",
      "cropped_path": "storage/uploads/abc....cropped.jpg",
      "moderation_status": "passed_local_heuristic"
    },
    "product_assets": [
      { "uuid": "...", "filename": "...", "content_hash": "...", ...,
        "kenburns_clip_path": "storage/tasks/<task_id>/uploaded-1.mp4",
        "screen_time_seconds": 4.5 }
    ],
    "auto_pexels_used": false
  }
}
```

For `visuals_mode == "auto"` renders, the audit log records `{ "visuals_mode": "auto", "auto_pexels_used": true }` to satisfy FR-021's "regardless of which mode was used" requirement.

**Rationale**:
- Specs 010 + 013 already extend `task.json`; adding a sibling key follows the established pattern. No new file = no new lifecycle to manage.
- Hash-included entries satisfy FR-020's "exact filenames, content hashes, and order" requirement and SC-001's verifiability ("ZERO Pexels frames, verified by audit log").
- Reading the audit programmatically is one `json.loads(open(script_json).read())["asset_audit"]` call.

**Alternatives considered**:
- Separate `asset_audit.json` file: rejected — additional file in the task directory adds cleanup-on-delete logic without payoff.
- Database row: rejected — Step 1 has no DB; the constitution's §Technology Constraints explicitly bars introducing one.

**Spec impact**: FR-020/021 are honored by this layout; no spec edit needed.

---

## R5 — Wizard visuals selector reuse pattern

**Decision**: Mirror spec 013's `script-mode.ts` helper module + pill-row UI exactly. New file `visualai-frontend/src/lib/visuals-mode.ts` exports:

```typescript
export type VisualsMode = "auto" | "user_uploaded";
export interface UploadedAsset {
  role: "model" | "product";
  filePath: string;        // server-side path returned by /api/v1/uploads/image
  filename: string;
  sizeBytes: number;
}
export interface WizardVisualsState {
  mode: VisualsMode;
  modelAsset: UploadedAsset | null;
  productAssets: UploadedAsset[];   // 0–3
}
export const PRISTINE_VISUALS: WizardVisualsState = {
  mode: "auto", modelAsset: null, productAssets: []
};
export function isPristineVisuals(s: WizardVisualsState): boolean { ... }
export function visualsStateToParams(s: WizardVisualsState): VisualsParams { ... }
```

The `visualsStateToParams` helper produces the wire shape consumed by the Layer-1 → Layer-3 generate proxy:

```typescript
type VisualsParams =
  | { visuals_mode: "auto" }
  | { visuals_mode: "user_uploaded";
      uploaded_model_path?: string;
      uploaded_product_paths: string[];   // 1–3 items required };
```

UI is a 2-pill row identical in styling to spec 013's script-mode pills, rendered inside the **Script & Voice** step beneath the script-mode pills and above the music selector.

**Rationale**:
- Spec 013's pattern (`script-mode.ts` helpers + `WizardScriptState` + `scriptStateToParams`) is the local idiom; users now see three identical pill-row controls in sequence (Script Mode / Visuals / Music). Consistency reduces UI cognitive load.
- The helper module is unit-testable in isolation (Vitest) without rendering the wizard — same pattern that gave spec 013 its 10-test frontend coverage.
- Mode-switch behavior preserves mode-specific state across switches (script 013's WMS-2..WMS-5 lessons): toggling from `user_uploaded` → `auto` → `user_uploaded` retains the uploaded asset references in component state but only emits them when the mode is `user_uploaded`.

**Alternatives considered**:
- Inline state in `page.tsx` with no helper module: rejected — couples test surface to React component rendering, slower test feedback loop.
- A single shared "render-mode" object covering script/visuals/music: rejected — three independent dimensions; coupling them now creates merge friction with future modes (e.g., subtitle-style selector).

**Spec impact**: FR-001 (now placing the selector in the Script & Voice step per Q2) is implemented exactly per the helper signature; FR-002 ("switching modes within an open wizard session MUST preserve script, voice, and other downstream choices") is satisfied because `WizardVisualsState` is sibling-state to `WizardScriptState`, not a replacement.

---

## Decisions consolidated

| ID | Decision | Spec impact | Files affected |
|---|---|---|---|
| R1 | Center-crop with EXIF correction; no saliency in Step 1 | None (FR-011 grants Step-1 latitude) | `app/controllers/v1/uploads.py` |
| R2 | Pillow verify + MIME + dimension guards; `MODERATION_REQUIRED=False` default | None (FR-010 already updated in spec) | `app/controllers/v1/uploads.py` |
| R3 | Per-image `ImageClip` with seeded random zoom + pan, write to `uploaded-<idx>.mp4` | None (FR-013 honored as written) | `app/services/material.py` |
| R4 | Extend `script.json` with `asset_audit` key | None (FR-020/021 honored) | `app/services/material.py` writer; consumers TBD |
| R5 | New `visuals-mode.ts` helper + pill row in Script & Voice step | None (FR-001 already updated for Q2) | `visualai-frontend/src/lib/visuals-mode.ts`, `…/components/wizard/visuals-selector.tsx` |

All five `NEEDS CLARIFICATION` items resolved. Phase 1 design unblocked.
