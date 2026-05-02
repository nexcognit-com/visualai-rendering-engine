# Contract: `apply_overlays()` Compositor

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 3](../data-model.md)

This contract defines the `apply_overlays()` function that composites a list of overlays onto a previously rendered MP4. The function lives in `app/services/overlays.py` (a new VisualAI-only file outside the Principle II fork-surface set, so it has no upstream-rebase concerns).

## Function signature

```python
def apply_overlays(
    input_mp4: str,
    overlays: list[Overlay],
    output_mp4: str | None = None,
) -> str:
    """Composite a list of overlays on top of a rendered MP4.

    Args:
        input_mp4: absolute filesystem path to a readable MP4 (typically
            the ``final-N.mp4`` produced by ``combine_videos``).
        overlays: ordered list of Overlay records (see schema.py). Empty
            list is a fast path that returns ``input_mp4`` unchanged.
        output_mp4: optional explicit output path. Defaults to
            ``<input_mp4 dir>/final-overlaid-<N>.mp4``.

    Returns:
        Absolute path to the produced MP4. When ``overlays`` is empty,
        returns ``input_mp4`` unchanged (no second pass run, no new file
        written).

    Raises:
        OverlayError: typed exception with a ``code`` attribute. See
            §Error semantics for the exhaustive list of codes.
    """
```

## Behavior contract

### Empty list — fast path

When `overlays == []`, the function MUST return `input_mp4` unchanged WITHOUT opening it, decoding it, or writing any new file. This is the SC-002 zero-regression contract: a wizard with no configured overlays must produce output byte-identical to today's pipeline.

### Single overlay — typical case

For each overlay in the list, in order:

1. **Logo**: build `ImageClip(source_path).with_duration(base.duration).resized(width=int(base.w * overlay.width_pct)).with_opacity(overlay.opacity).with_position((x, y))` where `(x, y)` is computed from `position` + `margin_px` per [research.md R2](../research.md).
2. **Rectangle**: build `ColorClip(size=(rect_w, rect_h), color=hex_to_rgb(overlay.color)).with_duration(base.duration).with_opacity(overlay.opacity).with_position((x, y))`.

Then `composite = CompositeVideoClip([base_clip, *overlay_clips])` and `composite.write_videofile(output_mp4, codec="libx264", audio_codec="aac", preset="medium")`.

### Multiple overlays — z-order

List order IS the z-order. The base video is the bottom layer; subsequent overlays composite on top in order. So `[rectangle, logo]` produces a video where the logo is on top of the rectangle (because it was added later).

### Output naming

Default output path: `<input_mp4_dir>/final-overlaid-<N>.mp4` where `<N>` is the same number as the input (e.g., `final-1.mp4` → `final-overlaid-1.mp4`). If a file with the default name already exists, the function raises `OverlayError("output_collision")` rather than overwriting silently — the caller (`task.py`) is expected to call with a fresh `task_id` per render so collisions shouldn't happen in practice.

### Encoder settings

`codec="libx264"`, `audio_codec="aac"`, `preset="medium"`. These match the upstream `combine_videos` settings ([video.py](../../app/services/video.py)) so the overlay output is visually consistent with non-overlay output. The `preset="medium"` choice trades encoding speed for quality — same trade-off the upstream pipeline already makes.

### Performance contract

| Metric | Target |
|---|---|
| Empty-list overhead | < 1 ms (just a list-length check, no file I/O) |
| Single-overlay overhead vs. base render time | ≤ 30% (SC-003) |
| Multi-overlay (5 overlays) overhead | ≤ 60% (linear-ish; encoder is the bottleneck) |
| Memory peak during composite | bounded by MoviePy's existing peak (no new memory pattern) |

## Error semantics

The function raises `OverlayError(code: str, **context)` for every recoverable failure. Callers catch by type and inspect `code`. The function MUST NOT swallow exceptions and produce overlay-less output silently (FR-013).

| `code` | Trigger | Caller response |
|---|---|---|
| `base_video_missing` | `input_mp4` doesn't exist or isn't a regular file | `task.py` marks task `state="failed"`, surfaces "render artifact missing" to user |
| `output_collision` | Default output path already exists on disk | log + retry with a different name (caller's choice); v1 just bubbles up |
| `logo_not_found` | An `Overlay.source_path` doesn't exist | `task.py` marks task `state="failed"`, wizard shows "logo file went missing — please re-upload" |
| `logo_unreadable` | `ImageClip(source_path)` throws (corrupt PNG, unsupported format slipped past upload validator) | wizard shows "logo file is corrupt or unsupported" |
| `compositor_write_failed` | `write_videofile` exception (FFmpeg crash, disk full, permission denied) | wizard shows "video processing failed — please retry" |
| `invalid_overlay_geometry` | Computed `(x, y, w, h)` for a rectangle would fall entirely outside the video bounds (impossible to render) | wizard shows "rectangle overlay placement is invalid" |

The function is allowed to clamp rectangle dimensions to fit within video bounds (treated as soft-fail with a logged warning per [research.md R5](../research.md)), but it MUST NOT clamp logos — a logo whose dimensions exceed the video would surface as `logo_unreadable` if MoviePy can't fit it, which is unlikely with the documented `width_pct` cap of 0.40 (40% of video width).

## Logging contract

Every call MUST emit at least:

1. INFO at entry: `"apply_overlays start input={input_mp4} overlays_count={len(overlays)}"`
2. INFO per overlay: `"compositing overlay {i}/{N} kind={kind} position={position}"`
3. INFO at exit: `"apply_overlays done output={output_mp4} elapsed_ms={elapsed}"`
4. ERROR on failure: `"apply_overlays failed code={code} context={context}"`

All log lines use loguru (matches MPT's existing logging discipline per the constitution's §Technology Constraints — Observability). The compositor doesn't have direct access to `task_id` or `tenant_id` — those are added by the caller (`task.py`) via `logger.bind(task_id=...)` before invoking.

## Stateless guarantee

The function is fully stateless:

- No global state read or written (no module-level caches, no class instance variables).
- No environment variables consulted at runtime (encoder settings are hardcoded constants).
- No database, no Redis, no network calls.
- Same inputs ALWAYS produce identical outputs (modulo non-determinism in MoviePy's encoder, which is shared with the upstream pipeline anyway).

This is what makes the function trivially testable.

## Verification

| Test ID | Inputs | Expected |
|---|---|---|
| C-1 | Empty overlays | Returns `input_mp4` unchanged; no new file written |
| C-2 | Single logo (top-right, 15% width, full opacity) | Returns new MP4; top-right region's mean RGB shifted toward logo color |
| C-3 | Single rectangle (bottom-left, white, 50% opacity) | Returns new MP4; bottom-left region's mean RGB shifted toward white |
| C-4 | Logo + rectangle stacked at same position | Returns new MP4; both visible; logo on top of rectangle (later in list = higher z) |
| C-5 | `Overlay.source_path = /nope.png` | Raises `OverlayError(code="logo_not_found")` |
| C-6 | `input_mp4 = /nope.mp4` | Raises `OverlayError(code="base_video_missing")` |
| C-7 | Corrupt PNG (bytes that don't decode) | Raises `OverlayError(code="logo_unreadable")` |
| C-8 | Output path that already exists | Raises `OverlayError(code="output_collision")` |

These eight tests are the contract surface for `/speckit.tasks` to schedule. Tests C-1 through C-3 cover the happy-path scenarios; C-4 covers stacking; C-5 through C-8 cover the error matrix.
