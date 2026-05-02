# Data Model: User-Uploaded Model & Product Assets

**Date**: 2026-05-02
**Spec**: [spec.md](spec.md) — see Key Entities §
**Plan**: [plan.md](plan.md)

The spec defines three logical entities: `Uploaded Asset`, `Asset Bundle`, `Generation Asset Audit`. In Step 1 (no DB), these are represented as **flat fields on `VideoParams`** plus a **JSON sub-document** appended to the existing `script.json` task file. When debt #2 repays in Step 2, these collapse into Neon tables owned by Layer 4 — but the wire shape and audit semantics defined here remain stable.

---

## 1. `VideoParams` extension (Pydantic)

Three new optional fields are added to `app/models/schema.py`'s `VideoParams` class:

```python
# Spec 006: visuals source mode. None = legacy behavior (Pexels-only Auto path,
# matches every existing render). "auto" is an explicit flavor of legacy.
# "user_uploaded" routes through the new in-material.py branch that converts
# uploaded image paths into Ken Burns clips.
visuals_mode: Optional[Literal["auto", "user_uploaded"]] = None

# Spec 006: filesystem path to the user's uploaded model image. Optional
# even when visuals_mode == "user_uploaded" (model image is optional per FR-003).
# Path is relative to repo root and points into storage/uploads/<uuid>.cropped.jpg
# (the 9:16-cropped derivative produced at upload time).
uploaded_model_path: Optional[str] = None

# Spec 006: ordered list of filesystem paths to the user's uploaded product
# images. 1–3 items required when visuals_mode == "user_uploaded".
uploaded_product_paths: List[str] = Field(default_factory=list)
```

### Validation rules

- `visuals_mode` accepts `None`, `"auto"`, `"user_uploaded"` only. All other values rejected by Pydantic.
- When `visuals_mode == "user_uploaded"`, `uploaded_product_paths` MUST contain 1–3 entries (validated in the controller before render dispatch — Pydantic alone can't express "this conditional on another field" cleanly without a model_validator; we use a model_validator).
- When `visuals_mode == "user_uploaded"` and `uploaded_product_paths` is empty, the controller returns 400 with `{"error_code": "no_product_assets"}`.
- All path values MUST resolve under `storage/uploads/` (basic path-traversal guard: `os.path.realpath(path).startswith(os.path.realpath(uploads_dir))`).
- `uploaded_model_path` and `uploaded_product_paths` MUST point to files that exist at render-dispatch time. Missing files cause 400 with `{"error_code": "asset_not_found", "missing_path": "..."}`.

### Backward compatibility

- `visuals_mode = None` preserves every existing render's behavior byte-for-byte: the Auto path runs unchanged, the new fields are simply ignored, and material.py's branch is never entered.
- Existing API consumers (the upstream MPT WebUI, any third-party integration) need not send these fields.

---

## 2. Upload-time response object (transient)

The `POST /api/v1/uploads/image` response is a plain JSON object — not persisted as an entity, just returned to the client so it can populate `uploaded_model_path` / `uploaded_product_paths` on the eventual generate request.

```json
{
  "path": "storage/uploads/abc123-def456-....cropped.jpg",
  "original_path": "storage/uploads/abc123-def456-....jpg",
  "size_bytes": 2048576,
  "mime_type": "image/jpeg",
  "source_width_px": 4032,
  "source_height_px": 3024,
  "cropped_width_px": 1080,
  "cropped_height_px": 1920,
  "content_hash": "sha256:91d33c..."
}
```

The client persists `path` (the cropped derivative) into wizard state and includes it in the eventual generate request. `original_path` is returned so the client can offer a "view original" link in a follow-up milestone (not used at v1).

---

## 3. Asset audit log (per-task JSON)

Written by `material.download_videos` to `storage/tasks/<task_id>/script.json` as a top-level `asset_audit` key. **Always written** (regardless of `visuals_mode`) per FR-021.

### Auto-mode shape

```json
{
  "asset_audit": {
    "visuals_mode": "auto",
    "auto_pexels_used": true,
    "pexels_clip_count": 7,
    "model_asset": null,
    "product_assets": []
  }
}
```

### User-uploaded-mode shape

```json
{
  "asset_audit": {
    "visuals_mode": "user_uploaded",
    "auto_pexels_used": false,
    "pexels_clip_count": 0,
    "model_asset": {
      "uuid": "abc123-def456-...",
      "filename": "founder-portrait.jpg",
      "content_hash": "sha256:91d33c...",
      "stored_path": "storage/uploads/abc123-....jpg",
      "cropped_path": "storage/uploads/abc123-....cropped.jpg",
      "kenburns_clip_path": "storage/tasks/<task_id>/uploaded-0.mp4",
      "moderation_status": "passed_local_heuristic",
      "screen_time_seconds": 4.5,
      "placement": "opening+closing"
    },
    "product_assets": [
      {
        "uuid": "ghi789-...",
        "filename": "dripper-top-down.jpg",
        "content_hash": "sha256:...",
        "stored_path": "storage/uploads/ghi789-....jpg",
        "cropped_path": "storage/uploads/ghi789-....cropped.jpg",
        "kenburns_clip_path": "storage/tasks/<task_id>/uploaded-1.mp4",
        "moderation_status": "passed_local_heuristic",
        "screen_time_seconds": 4.0,
        "placement": "middle-1"
      }
    ]
  }
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `visuals_mode` | `"auto" \| "user_uploaded"` | mirrors `VideoParams.visuals_mode`; defaulted to `"auto"` if `None` was on the params |
| `auto_pexels_used` | `bool` | `true` iff at least one frame in the final video originates from Pexels — gates SC-001's "ZERO Pexels frames" invariant |
| `pexels_clip_count` | `int` | number of Pexels-sourced clips in the final video |
| `model_asset` | object \| null | populated only when `uploaded_model_path` was non-null |
| `product_assets[]` | ordered list | matches input order (FR-015 requires sequential play in upload order) |
| `uuid` | string | the UUID4 portion of the stored filename |
| `content_hash` | `"sha256:<hex>"` | computed at upload; deduplication / verification key |
| `stored_path` | string | filesystem-relative from repo root; the original (pre-crop) file |
| `cropped_path` | string | filesystem-relative; the 9:16 derivative used by Ken Burns |
| `kenburns_clip_path` | string | filesystem-relative; the per-image mp4 (transient, lives with the task) |
| `moderation_status` | enum | `"passed_local_heuristic" \| "rejected_format" \| "rejected_dimensions" \| "passed_cloud_api"` (cloud values reserved for Step 2+) |
| `screen_time_seconds` | float | the segment duration this image owned in the final video; used by SC-007 verification |
| `placement` | string | one of: `"opening"`, `"opening+closing"` (model bookend), `"middle-N"` (1-indexed for products), `"closing"` |

### Verification queries

To verify SC-001 ("100% of `Use my own assets` renders contain ZERO Pexels frames"):

```python
audit = json.load(open(f"storage/tasks/{task_id}/script.json"))["asset_audit"]
assert audit["auto_pexels_used"] is False
assert audit["pexels_clip_count"] == 0
```

To verify FR-015 (model bookend placement):

```python
assert audit["model_asset"]["placement"] == "opening+closing"
assert all(a["placement"].startswith("middle-") for a in audit["product_assets"])
```

To verify SC-007 (≥ 2s per image):

```python
all_assets = [audit["model_asset"]] if audit["model_asset"] else []
all_assets += audit["product_assets"]
assert all(a["screen_time_seconds"] >= 2.0 for a in all_assets)
```

---

## 4. Filesystem layout

```text
storage/
├── uploads/
│   ├── abc123-def456-789ghi.jpg          # original — preserved per FR-018 + audit
│   ├── abc123-def456-789ghi.cropped.jpg  # 9:16 derivative — what the renderer uses
│   ├── ghi789-jkl012-345mno.png          # original
│   ├── ghi789-jkl012-345mno.cropped.jpg  # always re-encoded to JPEG for size
│   └── ...
└── tasks/
    └── <task_id>/
        ├── script.json                    # gains `asset_audit` key (this spec)
        ├── uploaded-0.mp4                 # Ken Burns clip for model_asset (when present)
        ├── uploaded-1.mp4                 # Ken Burns clips for product_assets[0..N]
        ├── uploaded-2.mp4
        ├── combined-1.mp4                 # existing — concat output
        └── final-1.mp4                    # existing — final render
```

When debt #2 repays in Step 2, all `storage/uploads/<uuid>.<ext>` paths gain a tenant prefix: `storage/uploads/<tenant_id>/<uuid>.<ext>`. The audit log shape is unchanged — only the path strings rotate.

### Lifecycle

- **Originals** (`storage/uploads/<uuid>.<ext>`): persist with the generation record per FR-018. Step 1 has no generation table; the lifecycle is "until the user manually deletes via a future asset library UI" — for now they accumulate. Cleanup deferred to debt #2 burndown.
- **Cropped derivatives** (`storage/uploads/<uuid>.cropped.jpg`): same lifetime as original.
- **Ken Burns clips** (`storage/tasks/<task_id>/uploaded-<idx>.mp4`): same lifetime as the task directory (typically retained for 7 days per the existing MPT task-cleanup policy).
- **Audit log** (`storage/tasks/<task_id>/script.json#asset_audit`): same lifetime as the task directory.

---

## 5. Frontend wizard state (TypeScript)

Lives in `visualai-frontend/src/lib/visuals-mode.ts` per [research.md R5](research.md#r5--wizard-visuals-selector-reuse-pattern):

```typescript
export type VisualsMode = "auto" | "user_uploaded";

export interface UploadedAsset {
  role: "model" | "product";
  filePath: string;          // server-returned cropped_path
  filename: string;
  sizeBytes: number;
  contentHash: string;
}

export interface WizardVisualsState {
  mode: VisualsMode;
  modelAsset: UploadedAsset | null;
  productAssets: UploadedAsset[];   // 0..3
}

export const PRISTINE_VISUALS: WizardVisualsState = {
  mode: "auto",
  modelAsset: null,
  productAssets: []
};

export function isPristineVisuals(s: WizardVisualsState): boolean { ... }

// Maps wizard state to the wire shape consumed by /api/v1/videos
export function visualsStateToParams(s: WizardVisualsState):
  | { visuals_mode: "auto" }
  | { visuals_mode: "user_uploaded";
      uploaded_model_path?: string;
      uploaded_product_paths: string[]; }
{ ... }
```

State machine:
- Pristine → user toggles to `user_uploaded` → uploads at least one product image → submit enabled.
- Switching `user_uploaded` → `auto` retains uploaded assets in state (so a re-toggle restores them) but `visualsStateToParams` emits only `{ visuals_mode: "auto" }` while in Auto.
- Removing the last product asset while in `user_uploaded` mode disables submit until at least one is re-uploaded.
