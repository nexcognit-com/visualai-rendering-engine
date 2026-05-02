# Contract: VisualParams wire shape

**Feature**: 006-user-uploaded-assets
**Layer 3 ↔ Layer 1 boundary**: `POST /api/v1/videos` request body + `app/models/schema.py` `VideoParams`

Defines exactly which fields cross the wire when a render job is dispatched. Three new optional fields extend the existing `VideoParams` model surgically — no refactor of existing fields, no breaking change for legacy callers.

## VideoParams extension

```python
# app/models/schema.py — additions only

class VideoParams(BaseModel):
    # ... existing fields preserved unchanged ...

    # Spec 006: visuals source mode. None preserves legacy behavior (Pexels-only
    # Auto path — every existing render). "auto" is an explicit flavor of legacy.
    # "user_uploaded" routes through material.download_videos's new branch.
    visuals_mode: Optional[Literal["auto", "user_uploaded"]] = None

    # Spec 006: filesystem path to user's uploaded model image. Optional even
    # when visuals_mode == "user_uploaded" (model image is optional per FR-003).
    # MUST resolve under storage/uploads/. Path is the cropped derivative
    # (storage/uploads/<uuid>.cropped.jpg).
    uploaded_model_path: Optional[str] = None

    # Spec 006: ordered list of paths to user's uploaded product images.
    # 1–3 entries required when visuals_mode == "user_uploaded".
    # MUST all resolve under storage/uploads/.
    uploaded_product_paths: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_visuals(self) -> "VideoParams":
        if self.visuals_mode == "user_uploaded":
            if not self.uploaded_product_paths:
                raise ValueError("no_product_assets")
            if len(self.uploaded_product_paths) > 3:
                raise ValueError("too_many_product_assets")
            for p in self.uploaded_product_paths:
                _require_under_uploads(p)
            if self.uploaded_model_path:
                _require_under_uploads(self.uploaded_model_path)
        return self
```

## Wire shape — frontend → MPT

The Layer-1 generate proxy (`visualai-frontend/src/app/api/generate/route.ts`) MUST forward exactly these new fields when present:

```typescript
type GenerateRequestExtension =
  | { /* visuals omitted entirely — legacy mode */ }
  | { visuals_mode: "auto" }
  | { visuals_mode: "user_uploaded";
      uploaded_model_path?: string;
      uploaded_product_paths: string[];   // 1–3 items };
```

Mapping rules in the proxy:

```typescript
// Inside POST /api/generate handler:
if (body.visuals_mode === "user_uploaded") {
  mptBody.visuals_mode = "user_uploaded";
  if (typeof body.uploaded_model_path === "string") {
    mptBody.uploaded_model_path = body.uploaded_model_path;
  }
  if (Array.isArray(body.uploaded_product_paths)) {
    mptBody.uploaded_product_paths = body.uploaded_product_paths.filter(
      (p): p is string => typeof p === "string"
    );
  }
} else if (body.visuals_mode === "auto") {
  mptBody.visuals_mode = "auto";
}
// Otherwise: omit visuals_mode entirely → MPT applies `None` default → legacy.
```

## Backward compatibility

| Caller | `visuals_mode` | Behavior |
|---|---|---|
| Legacy upstream MPT WebUI | omitted | `None` → Auto path → Pexels (current behavior) |
| VisualAI wizard pre-006 | omitted | same as above |
| VisualAI wizard 006+, Auto pill selected | `"auto"` | explicit Auto path → Pexels |
| VisualAI wizard 006+, My-assets pill selected | `"user_uploaded"` | new branch in `material.download_videos` |

`visuals_mode == None` and `visuals_mode == "auto"` produce **byte-identical renders** for the same other inputs. This is FR-008's zero-regression contract scope (mirroring spec 010's contract on `bgm_*` defaults).

## Error responses

| HTTP | `error_code` | When |
|---|---|---|
| 422 | `no_product_assets` | `visuals_mode == "user_uploaded"` but `uploaded_product_paths` is empty |
| 422 | `too_many_product_assets` | `len(uploaded_product_paths) > 3` |
| 422 | `path_outside_uploads` | Any of the paths fails the `os.path.realpath().startswith()` guard |
| 400 | `asset_not_found` | A path exists in the request but the file isn't on disk at render-dispatch time. Body includes `"missing_path": "..."` |

These errors are raised by the Pydantic model_validator OR the controller's pre-dispatch existence check — never inside the render workers.

## Test coverage (planned)

- VW-1: legacy default — request with no `visuals_mode` → defaults applied, no field emission. Round-trip equivalence: `VideoParams().model_dump(exclude_none=True)` does not contain `visuals_mode`, `uploaded_model_path`, or `uploaded_product_paths`.
- VW-2: explicit `"auto"` — Pydantic accepts it, model_validator passes, no path validation runs.
- VW-3: `"user_uploaded"` + 1 product path → valid.
- VW-4: `"user_uploaded"` + 3 product paths → valid.
- VW-5: `"user_uploaded"` + empty product paths → ValueError(`no_product_assets`).
- VW-6: `"user_uploaded"` + 4 product paths → ValueError(`too_many_product_assets`).
- VW-7: traversal attempt — `uploaded_product_paths=["../../etc/passwd"]` → ValueError(`path_outside_uploads`).
- VW-8: invalid literal — `visuals_mode="random"` → Pydantic rejection.
- VW-9: model image without products → ValueError(`no_product_assets`) (still requires at least one product per FR-003 + US2 acceptance scenario 3).
- VW-10: `visuals_mode = "auto"` + non-empty `uploaded_product_paths` → fields silently ignored by `download_videos` (auto path takes precedence; product paths retained on params for re-toggle scenarios per US3).
