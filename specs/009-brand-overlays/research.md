# Phase 0 Research: Static Brand Overlays on Rendered Videos

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-02

## R1 — MoviePy compositor pattern for the second pass

**Decision**: Use `moviepy.CompositeVideoClip([base, overlay_1, overlay_2, ...])` with each overlay built from existing MoviePy primitives:
- **Logo overlay** → `ImageClip(source_path).with_duration(base.duration).with_position((x, y)).with_opacity(opacity).resized(width=width_px)`
- **Rectangle overlay** → `ColorClip(size=(w, h), color=hex_to_rgb(color)).with_duration(base.duration).with_position((x, y)).with_opacity(opacity)`

The composite is written out via `composite.write_videofile(output_path, codec="libx264", audio_codec="aac", preset="medium")` — same encoder settings the existing pipeline uses so the overlay output is visually consistent with `final-N.mp4`.

**Rationale**: All four primitives (`CompositeVideoClip`, `ImageClip`, `ColorClip`, `VideoFileClip`) are already imported in [`app/services/video.py:12-15`](../../app/services/video.py). No new dependency. The pattern matches how `combine_videos` already composites text + background clips at `video.py:295` and `video.py:543`.

**Alternatives considered**:
- **FFmpeg-direct via subprocess** (skip MoviePy, run `ffmpeg -i base.mp4 -i logo.png -filter_complex overlay=...`) — rejected: faster but adds a parallel code path that has different failure modes than the rest of the pipeline. Sticking with MoviePy keeps error handling unified.
- **Two-pass MoviePy with file-system shuffling** (write logo as ImageSequence, re-read) — rejected: unnecessary I/O, no benefit.
- **Modifying `combine_videos` in-place to accept overlays** — rejected: violates Principle II (touches upstream code that should remain rebase-clean). The second-pass design keeps the upstream stitcher untouched.

## R2 — Position math (corner picker → pixel coordinates)

**Decision**: The five `position` enum values map to pixel coordinates derived from the base video's dimensions and the overlay's dimensions plus the configured `margin_px`:

| `position` | logo `(x, y)` | rectangle `(x, y)` |
|---|---|---|
| `top-left` | `(margin, margin)` | `(margin, margin)` |
| `top-right` | `(W - logo_w - margin, margin)` | `(W - rect_w - margin, margin)` |
| `bottom-left` | `(margin, H - logo_h - margin)` | `(margin, H - rect_h - margin)` |
| `bottom-right` | `(W - logo_w - margin, H - logo_h - margin)` | same |
| `center` | `(W/2 - logo_w/2, H/2 - logo_h/2)` | same |

Where `W` and `H` are the base video's width/height (1080 × 1920 for Mode 2's 9:16 aspect at default resolution), `logo_w` and `logo_h` are derived from the source image's aspect ratio scaled to `width_pct × W`, and `rect_w` / `rect_h` come from either the size preset (small=`W*0.15`, medium=`W*0.30`, large=`W*0.60`) or explicit `width_px` / `height_px`.

**Rationale**: Discrete corner enums avoid drag-positioning UI complexity while matching how marketers actually place logos on short ads (corners + center cover ~95% of real use). Margin defaults to 24 px (matches spec 001's spacing token at `--spacing-3`).

**Alternatives considered**:
- **Pixel coordinates as user input** (drag-positioning UI) — rejected per spec; deferred to v2.
- **Percentage-based positioning** (e.g., position as `{"x_pct": 0.85, "y_pct": 0.85}`) — rejected: more flexible but less brand-clean. Marketers think in corners, not percentages.

## R3 — Multipart upload endpoint shape

**Decision**: `POST /api/v1/uploads/logo` accepts a single multipart form with field name `file`. Returns 201 with `{"path": "storage/uploads/<uuid>.<ext>"}`. Validation:
- Allowed MIME types: `image/png`, `image/jpeg`, `image/webp`. Rejected with HTTP 400 + `{"error": "unsupported_format"}` for anything else.
- Max size 5 MB. Rejected with HTTP 413 + `{"error": "file_too_large"}` above the cap.
- Filename sanitization: extension extracted from MIME type (not the user-provided filename, to avoid path traversal), UUID4 generated for the storage filename.

The endpoint lives in a new file `app/controllers/v1/uploads.py` (registered alongside the existing `videos.py` controller).

**Rationale**: FastAPI's built-in `UploadFile` + `File()` parameter handles multipart parsing cleanly; `python-multipart` is already a transitive FastAPI dependency. Generating UUIDs server-side prevents collisions and removes path-traversal risk. Returning the path string (not a file ID) keeps `Overlay.source_path` schema-simple and matches the future Brand Library asset path convention.

**Alternatives considered**:
- **Base64-encoded upload in JSON body to `/api/generate`** — rejected: bloats request bodies, harder to debug, no streaming. Multipart is the standard.
- **Separate upload service** (e.g., a presigned-URL flow to direct-write-to-disk) — rejected: overkill for v1's local-filesystem layout. When Step 4 introduces R2/S3, the upload endpoint can be replaced with a presigned-URL handler without changing `Overlay.source_path`.
- **Cloud bucket upload at v1** — rejected per plan §Complexity Tracking.

## R4 — Frontend file upload pattern

**Decision**: The wizard's Overlays panel uses a hidden `<input type="file" accept="image/png,image/jpeg,image/webp" />` triggered by a styled button. On change, the file is `FormData`-wrapped and POSTed to the frontend's new `/api/upload-logo` route. The frontend route (server-side) re-multiparts the body to MPT's `/api/v1/uploads/logo`. The returned path is stored in React state, ready to be sent through `/api/generate` as part of the `overlays` array.

**Rationale**: Keeps the bearer-secret pattern intact (frontend → server route → MPT) so the same deployment pattern applies later when authenticated tenants are added. Uses native browser `FormData` so no upload library is needed. Pre-flight client-side validation (file size, MIME) gives instant feedback; server-side validation is the backstop.

**Alternatives considered**:
- **Direct browser → MPT upload** — rejected: would expose the MPT origin to the browser, bypassing the existing same-origin proxy contract.
- **`react-dropzone` or similar UI library** — rejected for v1: native input + a small component cover the job. Drop-zone UX can layer on top later if desired.

## R5 — Failure semantics

**Decision**: Per FR-013, every overlay-step failure surfaces as a typed error and halts the render. Specific failure modes:

| Failure | Detection | Response |
|---|---|---|
| Logo file path doesn't exist | `os.path.isfile(source_path) is False` at compositor entry | Raise `OverlayError("logo_not_found", path=source_path)` — render fails with `state="failed"`. |
| Logo file unreadable / corrupt PNG | `ImageClip(...)` throws during instantiation | Catch and re-raise as `OverlayError("logo_unreadable")`. |
| Rectangle outside video bounds | Computed `(x, y, x+w, y+h)` extends past `(0, 0, W, H)` | Clamp dimensions to fit; log a warning. (Treated as soft-fail; doesn't halt the render — the spec's edge case allows this.) |
| MoviePy `write_videofile` fails (FFmpeg crash, disk full) | exception during write | Re-raise as `OverlayError("compositor_write_failed")`. |
| Pre-existing `final-N.mp4` missing | `os.path.isfile(input_mp4) is False` | Raise `OverlayError("base_video_missing")`. Indicates pipeline corruption upstream. |

The compositor MUST NOT swallow exceptions and produce overlay-less output silently — that would violate FR-013 ("MUST NOT silently fall back").

**Rationale**: A render that ignores user intent without notifying them is the original problem this feature is designed to solve. Failing loud is the explicit goal.

**Alternatives considered**:
- **Soft-fail to overlay-less output with a warning surfaced in My Assets** — rejected per FR-013. Even one silent fallback would re-introduce the problem.

## R6 — Forward-compatibility hook for Brand Library (Step 5)

**Decision**: `Overlay.source_path` accepts any filesystem-relative path string. Three resolution layers, evaluated in order at compositor entry:

1. **Per-render upload** (today): `storage/uploads/<uuid>.<ext>` — the path returned by `POST /api/v1/uploads/logo`.
2. **Brand Library asset** (Step 5+): `brand-library/<tenant_id>/<asset_id>.<ext>` — paths emitted by the future Brand Library endpoint.
3. **Absolute path** (operator-only, dev/test): any absolute path the engine can read. Useful for smoke tests that pre-stage a known-good logo.

Resolution is filesystem-only at v1; in Step 4 when assets move to R2/S3, the resolver gains a remote-fetch branch but the `Overlay` model doesn't change.

**Rationale**: The path-string contract is the cheapest forward-compatible shape — string in, MoviePy clip out. Future asset sources fit through the same interface.

**Alternatives considered**:
- **Schema with `kind: upload | brand_library | url` discriminator** — rejected: explicit but premature. The path-string convention is enough for v1; a discriminator can be added without a breaking change later.
- **Always upload, never reference Brand Library** — rejected: forces tenants to re-upload their logo every render in the future. Defeats the Brand Library purpose.

## R7 — Smoke test layout

**Decision**: One pytest test at `test/services/test_overlays.py` covering:

1. **Happy path — logo composite**: build a 1-second `ColorClip` (red 1080×1920) as the stub base; build a known-good 200×200 transparent PNG via Pillow; call `apply_overlays(stub, [Overlay(kind="logo", position="top-right", source_path=tmp_png, ...)])`; assert the output MP4 exists, opens cleanly, and the top-right region's mean RGB has shifted from pure red toward the logo's color (proves the composite landed).
2. **Happy path — rectangle composite**: similar stub; call with a `Overlay(kind="rectangle", color="#FFFFFF", ...)`; assert the bottom-center region's mean RGB shifted toward white.
3. **No-overlays fast path**: `apply_overlays(stub, [])` returns the input path unchanged (zero second pass).
4. **Logo missing**: `apply_overlays(stub, [Overlay(source_path="/nope.png", ...)])` raises `OverlayError` with `code="logo_not_found"`.

The test uses `tmp_path` fixtures + Pillow to manufacture the synthetic PNG; no test fixtures are committed to the repo.

**Rationale**: Per the constitution's Development Workflow rule ("new mode code requires at least one smoke test exercising the rendering path with mocked Layer 2 inputs"), shipping a smoke test alongside the feature is mandatory. The test is fast (< 5 s wall clock with a 1-second stub clip) so it can run on every CI / pre-commit hook.

**Alternatives considered**:
- **Visual diff testing with a golden MP4** — rejected: byte-exact comparison is fragile across MoviePy/FFmpeg versions and OS-level codec differences. Mean-RGB-region check is robust enough for smoke.
- **End-to-end test through the wizard + Pexels API** — rejected for unit smoke: integration tests are good but should be a separate `test/integration/` track, not blocking this feature's ship.

## R8 — Open follow-ups (not blockers for v1)

These are noted for future iteration; not in v1 scope:

1. **Natural-language overlay parsing**: an LLM step that reads "add my logo to the bottom right at 80% opacity" and emits structured `Overlay` records. Layers cleanly on top of the structured UI.
2. **Animated overlays**: fade-in, slide-from-edge, or pulse animations. MoviePy supports these via `clip.with_effects()` — would extend `Overlay` with an `animation` field.
3. **Text overlays**: titles, captions, "watch until end" prompts. Different shape from logo/rectangle (font, size, weight, content) — likely warrants its own `kind: "text"` discriminator.
4. **Brand Library**: persistent per-tenant asset storage. The `source_path` field is already shaped for this; the feature is about the storage layer + UI, not the overlay model.
5. **Drag-positioning UI**: pixel-precise placement instead of corner picker. Would extend `Overlay` with `position: {x, y}` as an alternative to the enum.

## Summary

All NEEDS-CLARIFICATION items in the Technical Context resolved. No new dependencies. The compositor design slots into the existing pipeline at exactly one point (after `combine_videos`), keeps upstream code rebase-clean, fails loud on every error, and ships with smoke-test coverage. Forward-compatibility hooks are in place for Brand Library, animated overlays, and text overlays — all of which can ship without breaking the v1 schema.
