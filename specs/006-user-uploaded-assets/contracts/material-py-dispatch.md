# Contract: `material.py` dispatch on `visuals_mode`

**Feature**: 006-user-uploaded-assets
**File**: `app/services/material.py`
**Surface**: `download_videos()` — fork-surface file per Principle II

The branching point. When `visuals_mode == "user_uploaded"`, `download_videos` returns user-derived clip paths instead of Pexels-fetched ones. **No `task.py` edit** — the new branch lives entirely inside `material.py`.

## Function signature change

`download_videos` gains the rendered `VideoParams` reference (or its relevant subset) so it can read the new fields. Per spec 013's lesson (don't grow the parameter list further), we add **one** new parameter wrapping the visuals context:

```python
# app/services/material.py — modified signature

def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    # Spec 006 additions:
    visuals_mode: Optional[Literal["auto", "user_uploaded"]] = None,
    uploaded_model_path: Optional[str] = None,
    uploaded_product_paths: Optional[List[str]] = None,
) -> List[str]:
    """Return ordered clip paths for the renderer.

    Dispatch:
      - visuals_mode is None or "auto": existing Pexels/Pixabay behavior unchanged.
      - visuals_mode is "user_uploaded": ignore search_terms + source, return
        Ken Burns mp4s built from uploaded_*_paths.
    """
    if visuals_mode == "user_uploaded":
        return _build_clips_from_uploads(
            task_id=task_id,
            model_path=uploaded_model_path,
            product_paths=uploaded_product_paths or [],
            audio_duration=audio_duration,
            video_aspect=video_aspect,
        )

    # ... existing Pexels/Pixabay code path unchanged ...
```

`task.py`'s call site is updated to pass the three new params via `**kwargs`-compatible additions; the existing `task.py` call signature is preserved (no new touch line).

> **Important**: this approach DOES require updating the `task.py` call site to pass the new fields through. **That is one new touch line in `task.py`**, which would extend debt #5. To avoid that, the implementation MUST instead read the new fields from a shared per-task context. Two options:
>
> **Option α (preferred)**: extend `download_videos` to read from `task.py`'s caller-provided params object passed through the existing `params.video_source` / aspect / concat_mode chain. Specifically, since `task.py:179` already reaches into `params.video_source`, `params.video_aspect`, etc., the cleanest path is to thread `params` directly: `material.download_videos(task_id, search_terms, params, audio_duration)`. **This IS one parameter rename in `task.py`**. After consultation with the Q3 answer (debt #5 stays unchanged), the implementation MUST instead use Option β.
>
> **Option β (chosen, per Q3)**: read uploaded paths from a JSON sidecar at `storage/tasks/<task_id>/visuals.json`, written by the upload controller before dispatch. `download_videos` reads the sidecar internally if `os.path.exists(...)`. Adds zero parameters; zero `task.py` changes; one new file in the task dir.

**Decision**: implementation uses **Option β (sidecar)**. The sidecar is written by the controller (`/api/v1/videos` POST handler) at the moment it constructs the task — same lifetime as `task_id`. `download_videos` reads it internally. This honors Q3's "no `task.py` edit" guarantee literally; debt #5's line count stays unchanged.

## Sidecar shape: `storage/tasks/<task_id>/visuals.json`

Written by the controller before render dispatch (only when `visuals_mode == "user_uploaded"`). Absent for legacy / `auto` renders.

```json
{
  "visuals_mode": "user_uploaded",
  "uploaded_model_path": "storage/uploads/abc.....cropped.jpg",
  "uploaded_product_paths": [
    "storage/uploads/ghi.....cropped.jpg",
    "storage/uploads/jkl.....cropped.jpg"
  ]
}
```

`download_videos` reads it via:

```python
def _read_visuals_sidecar(task_id: str) -> Optional[dict]:
    p = path.join(utils.task_dir(task_id), "visuals.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)
```

Branching logic at the top of the existing `download_videos`:

```python
def download_videos(task_id, search_terms, source, ...):
    sidecar = _read_visuals_sidecar(task_id)
    if sidecar and sidecar.get("visuals_mode") == "user_uploaded":
        return _build_clips_from_uploads(
            task_id=task_id,
            model_path=sidecar.get("uploaded_model_path"),
            product_paths=sidecar.get("uploaded_product_paths", []),
            audio_duration=audio_duration,
            video_aspect=video_aspect,
        )
    # ... existing Pexels/Pixabay code path ...
```

## `_build_clips_from_uploads` semantics

```python
def _build_clips_from_uploads(
    task_id: str,
    model_path: Optional[str],
    product_paths: List[str],
    audio_duration: float,
    video_aspect: VideoAspect,
) -> List[str]:
    """Return ordered clip paths for combine_videos.

    Order:
      [model_clip?, product_clip_1, product_clip_2, product_clip_N, model_clip?]
                  -- bookended only when model_path is non-null --

    Each image becomes one Ken Burns mp4 of duration ~equal-share of audio_duration,
    with min 2s per clip enforced (FR-014 + FR-016).
    """
    ...
```

### Per-clip duration calculation

```python
n_clips = len(product_paths) + (2 if model_path else 0)  # model bookended
total = audio_duration
per_clip = max(2.0, total / n_clips)                     # FR-014 + FR-016
# When sum(per_clip) > total, last clip is truncated by combine_videos's
# existing trimming logic.
```

### Ken Burns helper (private)

```python
def _make_kenburns_clip(image_path: str, duration: float, output_path: str,
                       seed: int) -> None:
    """Write a Ken Burns mp4 to output_path. Pure side-effect; no return."""
    rng = random.Random(seed)
    zoom_in = rng.choice([True, False])
    zoom_pct = rng.uniform(0.04, 0.08)
    pan_dx = rng.uniform(-0.03, 0.03)
    pan_dy = rng.uniform(-0.03, 0.03)
    # MoviePy ImageClip + .resize(lambda t: ...) + .set_position(lambda t: ...)
    # CompositeVideoClip → write_videofile(output_path, codec="libx264", fps=30)
```

Seed is derived from `int(hashlib.sha256(image_path.encode()).hexdigest()[:8], 16)` so the same image always gets the same motion (idempotent renders).

## Audit log emission

`_build_clips_from_uploads` MUST also write the `asset_audit` entry to `storage/tasks/<task_id>/script.json` per [data-model.md §3](../data-model.md#3-asset-audit-log-per-task-json). Specifically:

1. Read existing `script.json` (must exist — `task.py:269` writes it before this point).
2. Compute SHA-256 hash of each uploaded original (`storage/uploads/<uuid>.<ext>`, NOT the cropped derivative — the hash identifies the user's source).
3. Build the `asset_audit` block with `visuals_mode`, `model_asset`, `product_assets[]`, `auto_pexels_used: false`, `pexels_clip_count: 0`.
4. Atomic-rewrite `script.json` (write to temp, rename) so a crash mid-update doesn't corrupt the file.

For the legacy / `auto` path, the existing `download_videos` is augmented with a small post-pass that writes the `auto_pexels_used: true, pexels_clip_count: <n>` audit block. This is the **one new responsibility** of the existing branch — its only behavioral change.

## Backward compatibility

- When `visuals.json` sidecar is absent: existing Pexels behavior is byte-for-byte preserved (the new branching code is a single `if sidecar and ...:` short-circuit).
- The auto-mode audit-log emission is additive — readers that don't expect `asset_audit` simply ignore it (it's a new top-level key in `script.json`, no schema strictness).
- `_build_clips_from_uploads` and `_make_kenburns_clip` are private (`_`-prefixed) — not exposed for re-use; no public API surface created.

## Test coverage (planned)

- MD-1: `visuals.json` absent → legacy Pexels code path runs (mock `search_videos_pexels`).
- MD-2: `visuals.json` present, `visuals_mode="auto"` → still legacy path (mode wins over field presence — defensive).
- MD-3: `visuals.json` present, `visuals_mode="user_uploaded"`, 1 product path → returns 1 clip path; clip exists on disk; matches `storage/tasks/<task_id>/uploaded-1.mp4`.
- MD-4: ditto, 3 product paths + 1 model → returns 5 clip paths in order `[model, p1, p2, p3, model]`.
- MD-5: ditto, 0 product paths (sidecar malformed) → raises ValueError before any clip is written.
- MD-6: per-clip duration math — 30s audio, 3 product clips, no model → each clip is 10s.
- MD-7: short-audio edge — 4s audio, 3 product clips → each clip is exactly 2s (FR-014 floor).
- MD-8: idempotent seeding — calling twice with same image produces deterministic clip bytes (SHA-256 of clip mp4 matches).
- MD-9: audit log written — `script.json` after `_build_clips_from_uploads` contains `asset_audit.visuals_mode == "user_uploaded"`, content_hashes match `hashlib.sha256(open(original).read())`.
- MD-10: legacy auto path also writes audit — `asset_audit.visuals_mode == "auto"`, `auto_pexels_used == True`, `pexels_clip_count` matches the number of clips returned.
