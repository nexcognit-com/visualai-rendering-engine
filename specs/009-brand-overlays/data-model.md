# Phase 1 Data Model: Static Brand Overlays

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

The feature introduces three first-class entities and one extension to an existing entity. All Pydantic models live in `app/models/schema.py` (fork-surface, already touched in Step 1). All entities are in-process — there is no database table.

---

## Entity 1 — `Overlay` (new Pydantic model)

**File**: `app/models/schema.py`
**Cardinality**: 0–5 per `VideoParams` (FR-010)
**Discriminator**: `kind` field — one of `"logo"` or `"rectangle"`

### Schema (Pydantic v2)

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

OverlayKind = Literal["logo", "rectangle"]
OverlayPosition = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]
RectangleSizePreset = Literal["small", "medium", "large"]

class Overlay(BaseModel):
    """One static overlay composited on top of a rendered video.

    Discriminated by ``kind``: logos require ``source_path``; rectangles
    require ``color`` plus EITHER ``size_preset`` OR explicit
    ``width_px``/``height_px`` (XOR via ``model_validator``).
    """
    kind: OverlayKind
    position: OverlayPosition
    opacity: float = Field(ge=0.1, le=1.0, default=1.0)
    margin_px: int = Field(ge=0, le=200, default=24)

    # logo-only fields
    source_path: Optional[str] = None
    width_pct: Optional[float] = Field(ge=0.05, le=0.40, default=None)

    # rectangle-only fields
    color: Optional[str] = None             # hex string, e.g. "#FFFFFF" or "#3B82F6"
    size_preset: Optional[RectangleSizePreset] = None
    width_px: Optional[int] = Field(ge=10, le=1920, default=None)
    height_px: Optional[int] = Field(ge=10, le=1920, default=None)

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> "Overlay":
        if self.kind == "logo":
            if not self.source_path:
                raise ValueError("logo overlay requires source_path")
            if self.width_pct is None:
                self.width_pct = 0.15  # default for logos
        elif self.kind == "rectangle":
            if not self.color:
                raise ValueError("rectangle overlay requires color")
            has_preset = self.size_preset is not None
            has_explicit = self.width_px is not None and self.height_px is not None
            if has_preset == has_explicit:
                raise ValueError(
                    "rectangle overlay requires EITHER size_preset OR (width_px AND height_px), not both / neither"
                )
            # rectangle default opacity is 0.5, not 1.0; only apply if user left default
            if self.opacity == 1.0:
                self.opacity = 0.5
        return self
```

### Field-by-field

| Field | Type | Required when | Constraints | Default | Source |
|---|---|---|---|---|---|
| `kind` | `Literal["logo", "rectangle"]` | always | one of two values | — | FR-001/FR-002/FR-003 |
| `position` | `Literal["top-left", ...]` (5 values) | always | one of five values | — | FR-002/FR-003, R2 of research.md |
| `opacity` | `float` | always | 0.1–1.0 | `1.0` (logo), `0.5` (rectangle, applied via validator) | FR-002/FR-003 |
| `margin_px` | `int` | always | 0–200 | `24` (matches spec 001 spacing-3 token) | FR-002 |
| `source_path` | `Optional[str]` | required if `kind=="logo"` | non-empty string; resolves to a readable file at compositor time | `None` | FR-002, FR-012 |
| `width_pct` | `Optional[float]` | logo only | 0.05–0.40 | `0.15` (15% of video width) | FR-002 |
| `color` | `Optional[str]` | required if `kind=="rectangle"` | hex string `^#[0-9A-Fa-f]{6}$` | `None` | FR-003 |
| `size_preset` | `Optional[Literal["small","medium","large"]]` | rectangle, if explicit dims absent | XOR with `width_px`+`height_px` | `None` | FR-003 |
| `width_px` | `Optional[int]` | rectangle, if preset absent | 10–1920; both `width_px` and `height_px` MUST be present together | `None` | FR-003 |
| `height_px` | `Optional[int]` | rectangle, if preset absent | 10–1920 | `None` | FR-003 |

### Validation rules summary

1. Logo overlays MUST have `source_path`; rectangles MUST have `color`.
2. Rectangles MUST specify EITHER `size_preset` OR (`width_px` AND `height_px`) — never both, never neither (XOR enforced).
3. Opacity defaults differ by kind (1.0 for logo, 0.5 for rectangle) — captured in `model_validator`.
4. Hex color format is validated with a regex at the model layer; downstream `apply_overlays()` parses to RGB tuples.

### Lifecycle

`Overlay` instances are constructed once per render request, attached to `VideoParams.overlays`, passed straight through to `apply_overlays()`. They are never persisted to disk or DB — the path strings inside them ARE persisted (as part of `script.json` written by MPT for each task).

---

## Entity 2 — `Logo Asset` (filesystem artifact)

**Storage**: `storage/uploads/<uuid>.<ext>` (single shared dir at v1; tenant-scoped under `storage/uploads/<tenant_id>/<uuid>.<ext>` once debt #2 repays in Step 2).
**Format**: PNG, JPG, or WebP. PNG preferred for alpha channel.
**Lifecycle**: created by `POST /api/v1/uploads/logo`; referenced by `Overlay.source_path`; never auto-deleted at v1 (operator does manual cleanup if disk pressure rises).
**Constraints**:
- Max size: 5 MB (FR-002, enforced at upload endpoint).
- MIME types accepted: `image/png`, `image/jpeg`, `image/webp` (R3).
- Filename is a server-generated UUID4 + extension derived from MIME, NOT the user's filename (avoids path traversal, collisions).

### Per-render persistence

The path string lives inside the task's `script.json` artifact (already produced by MPT) under the `params.overlays[].source_path` field. This means My Assets can already display "this render had overlays" without schema changes — the existing `/api/history` endpoint just needs a tiny enrichment to read the field.

---

## Entity 3 — `Composite Pass` (stateless function)

**Signature**: `apply_overlays(input_mp4: str, overlays: list[Overlay], output_mp4: str | None = None) -> str`
**File**: `app/services/overlays.py` (new — VisualAI-only, NOT in fork-surface)
**Returns**: path to the new MP4 file with overlays composited (typically `<task_dir>/final-overlaid-1.mp4`)

### Inputs / outputs

| Direction | Param | Shape | Notes |
|---|---|---|---|
| in | `input_mp4` | absolute filesystem path to a readable MP4 | typically `final-1.mp4` |
| in | `overlays` | `list[Overlay]` (length 0–5) | empty list → returns `input_mp4` unchanged (fast path) |
| in | `output_mp4` | optional explicit output path | defaults to `<input_mp4 dir>/final-overlaid-<N>.mp4` |
| out | `str` | absolute filesystem path to the produced MP4 | when overlays empty, equals `input_mp4` |

### State transitions

The function is stateless. It does NOT consult any database, cache, or session. It opens the input video, composites the overlays in list order (later overlays render on top), and writes the output. The encoder settings (codec=`libx264`, audio_codec=`aac`, preset=`medium`) match the upstream `combine_videos` for visual consistency.

### Error semantics

Per R5 of research.md and FR-013, the function raises a typed `OverlayError(code, **context)` for every failure. The caller (`task.py`) catches `OverlayError`, logs the failure with `task_id` context, and marks the task `state="failed"` so the wizard surfaces a typed error in My Assets.

| Error code | Trigger | HTTP equivalent if propagated |
|---|---|---|
| `base_video_missing` | `input_mp4` doesn't exist or unreadable | 500 |
| `logo_not_found` | `Overlay.source_path` doesn't exist | 400 |
| `logo_unreadable` | `ImageClip(...)` throws on instantiation | 400 |
| `compositor_write_failed` | `write_videofile` exception (FFmpeg crash, disk full) | 500 |

The function MUST NOT swallow these — silent fallback to overlay-less output is a v1 violation regardless of how minor.

---

## Entity 4 — `VideoParams.overlays` (extension to existing entity)

**File**: `app/models/schema.py` (existing fork-surface file)
**Change**: extend `VideoParams` with `overlays: list[Overlay] = []`

### Schema diff (conceptual)

```python
class VideoParams(BaseModel):
    # ... existing fields (video_subject, video_script, mode, video_aspect, ...) ...
    overlays: list[Overlay] = Field(default_factory=list, max_length=5)
```

### Validation rules

- `overlays` MUST be a list (Pydantic enforces this).
- Length MUST be ≤ 5 (FR-010, enforced via `max_length=5`).
- Each element MUST validate as a complete `Overlay` (Pydantic recursive validation handles this).
- Default is empty list — preserves the "zero regression on no-overlays-render" contract (SC-002).

### Backwards compatibility

- Existing render requests that omit `overlays` validate cleanly — Pydantic's `default_factory=list` produces an empty list.
- Existing `script.json` files without an `overlays` field are still parseable for replay/history.
- The frontend's existing `/api/generate` body shape is augmented (not broken) with the new field.

---

## Cross-entity relationships

```text
                  POST /api/v1/uploads/logo
                          │
                          ▼
                 storage/uploads/<uuid>.png    (Logo Asset, Entity 2)
                          │
                          │ source_path string
                          ▼
        Overlay(kind="logo", source_path="...", ...)   (Entity 1)
                          │
                          │ N×
                          ▼
         VideoParams(overlays=[Overlay, Overlay, ...])  (Entity 4)
                          │
                          │ task.py
                          ▼
   combine_videos(...) → final-1.mp4
                          │
                          │ if overlays present
                          ▼
     apply_overlays(final-1.mp4, overlays)              (Composite Pass, Entity 3)
                          │
                          ▼
                   final-overlaid-1.mp4   (path returned to frontend)
```

**Source-of-truth invariants**:

- The `Overlay` model is the SINGLE source of truth for what an overlay means. The compositor consumes it; the wizard produces it; the upload endpoint produces only the `source_path` it carries.
- The compositor NEVER consults the wizard's UI state. All overlay decisions are encoded in the `Overlay` records by the time `apply_overlays()` is called.
- The `source_path` field is the SINGLE point where storage layout assumptions live. Today it points at `storage/uploads/`; in Step 2 it scopes per-tenant; in Step 4 it points at R2/S3. The model itself doesn't care.

---

## What is NOT modeled (deliberately)

- **Render-time logo cache**: each render re-reads the PNG from disk. No in-process caching at v1 (overlays-per-render is rare; the second-pass already amortizes I/O).
- **Animated overlays** (fade, slide, pulse): future addition via an optional `animation` field. The spec defers this to v2.
- **Text overlays**: a separate `kind: "text"` discriminator with `content`, `font`, `size`, `weight` fields. Not in v1 scope.
- **Per-overlay z-index**: list order IS the z-index. A future `z` field would allow non-contiguous insertion; not needed at v1.
- **Brand Library asset records**: handled by Step 5's feature, not by this spec. The `source_path` field is the only schema hook between this feature and Brand Library.
- **Telemetry events** ("overlay applied", "overlay rejected"): no observability infrastructure in scope; rely on existing loguru logs.
