# Contract: Overlay Schema

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 1](../data-model.md)

This contract defines the wire shape of `Overlay` objects sent from the frontend to MPT's `/api/v1/videos`. It is the single source of truth for what an overlay means; both client (`visualai-frontend`) and server (`app/models/schema.py`) MUST match this shape exactly.

## JSON shape (logo overlay)

```json
{
  "kind": "logo",
  "position": "bottom-right",
  "opacity": 1.0,
  "margin_px": 24,
  "source_path": "storage/uploads/0e0a4f7a-2a1b-4d3c-9e9f-7c8d2a1b4d3c.png",
  "width_pct": 0.15
}
```

## JSON shape (rectangle overlay — preset size)

```json
{
  "kind": "rectangle",
  "position": "bottom-center",
  "opacity": 0.5,
  "margin_px": 24,
  "color": "#3B82F6",
  "size_preset": "medium"
}
```

> Note: `bottom-center` is NOT in the v1 position enum. The five accepted values are `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center`. A "bottom-center" use case can be approximated with `position: "center"` plus a tall margin, OR added in v2 by extending the enum.

## JSON shape (rectangle overlay — explicit dimensions)

```json
{
  "kind": "rectangle",
  "position": "top-left",
  "opacity": 0.7,
  "margin_px": 16,
  "color": "#FFF86B",
  "width_px": 320,
  "height_px": 80
}
```

## Field-level contract

| Field | Type | Required when | Constraint |
|---|---|---|---|
| `kind` | string | always | one of `["logo", "rectangle"]` |
| `position` | string | always | one of `["top-left", "top-right", "bottom-left", "bottom-right", "center"]` |
| `opacity` | float | always | 0.1 ≤ x ≤ 1.0 |
| `margin_px` | integer | always | 0 ≤ x ≤ 200 |
| `source_path` | string | `kind == "logo"` only | non-empty; resolves to a readable file at compositor entry |
| `width_pct` | float | `kind == "logo"` only | 0.05 ≤ x ≤ 0.40; defaults to 0.15 if omitted |
| `color` | string | `kind == "rectangle"` only | matches `^#[0-9A-Fa-f]{6}$` |
| `size_preset` | string | `kind == "rectangle"`, XOR with `width_px`+`height_px` | one of `["small", "medium", "large"]` |
| `width_px` | integer | `kind == "rectangle"`, XOR with `size_preset` | 10 ≤ x ≤ 1920; MUST be paired with `height_px` |
| `height_px` | integer | `kind == "rectangle"`, XOR with `size_preset` | 10 ≤ x ≤ 1920; MUST be paired with `width_px` |

## Enclosing context — `VideoParams.overlays`

`Overlay` objects appear inside `VideoParams.overlays` (a list). The list:

- MUST be present in every render request (default `[]`)
- MUST contain ≤ 5 items (FR-010)
- MAY mix `kind`s (e.g., one logo + one rectangle in the same render)
- ORDER MATTERS — overlays render in list order, with later items composited on top of earlier items.

## Validation behavior

The server-side `Overlay` Pydantic model enforces every constraint above plus the discriminated-union XOR rule (rectangle requires preset OR explicit dims, never both, never neither). Validation failures return HTTP 422 from `/api/v1/videos` with the standard FastAPI error body identifying the offending field.

The client SHOULD validate locally before submission to give faster feedback; server-side validation is the authoritative backstop.

## Forward-compatibility

| v2 extension | How v1 schema accommodates |
|---|---|
| Brand Library asset references | `source_path` is a free-form string; v1 paths point at `storage/uploads/`, v2 paths point at `brand-library/<tenant>/<asset>.png`. No schema change. |
| Animated overlays | New optional `animation: "fade-in" \| "slide-from-edge" \| "pulse"` field on `Overlay`. Default `null`. Existing v1 overlays validate unchanged. |
| Text overlays | New `kind: "text"` discriminator with its own required fields (`content`, `font_family`, `font_weight`, `font_size_px`). v1 overlays validate unchanged. |
| Drag-positioning UI | New optional `position_px: {x: int, y: int}` field that overrides the `position` enum when present. Existing v1 overlays validate unchanged. |
| Per-overlay z-index | Today's "list order is z-order" remains the default; an optional `z: int` field would allow non-contiguous reordering without breaking v1 records. |

## Examples (golden behavior)

### Example 1 — Single logo

```json
{
  "video_subject": "Diamond engagement ring",
  "video_script": "",
  "mode": "short",
  "video_aspect": "9:16",
  "overlays": [
    {
      "kind": "logo",
      "position": "bottom-right",
      "opacity": 1.0,
      "margin_px": 24,
      "source_path": "storage/uploads/0e0a4f7a-2a1b-4d3c-9e9f-7c8d2a1b4d3c.png",
      "width_pct": 0.15
    }
  ]
}
```

### Example 2 — No overlays (current behavior)

```json
{
  "video_subject": "Diamond engagement ring",
  "video_script": "",
  "mode": "short",
  "video_aspect": "9:16",
  "overlays": []
}
```

The compositor short-circuits when `overlays` is empty; output is byte-identical to today's pipeline.

### Example 3 — Logo + rectangle stacked

```json
{
  "video_subject": "Limited-time offer landing page",
  "mode": "short",
  "video_aspect": "9:16",
  "overlays": [
    {
      "kind": "rectangle",
      "position": "top-left",
      "opacity": 0.6,
      "margin_px": 24,
      "color": "#3B82F6",
      "size_preset": "small"
    },
    {
      "kind": "logo",
      "position": "top-left",
      "opacity": 1.0,
      "margin_px": 32,
      "source_path": "storage/uploads/<uuid>.png",
      "width_pct": 0.10
    }
  ]
}
```

The rectangle composites first; the logo composites on top of it (because it's later in the list). The 32 px margin on the logo nests it inside the rectangle's 24 px-margin position.

## What this contract does NOT cover

- **Endpoint contracts**: see [`upload-endpoint.md`](./upload-endpoint.md) for `/api/v1/uploads/logo` shape.
- **Compositor function contract**: see [`compositor-contract.md`](./compositor-contract.md) for `apply_overlays()` semantics.
- **UI contracts**: the wizard's overlay panel layout / labels are visual-design concerns covered by spec 001 (UI Style) and the wizard's own implementation, not by this schema contract.
