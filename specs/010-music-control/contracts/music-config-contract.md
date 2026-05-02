# Contract: Music Configuration Wire Shape

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 1](../data-model.md)

This contract documents the wire-shape semantics of the EXISTING `bgm_type` / `bgm_file` / `bgm_volume` fields on `VideoParams`. **No schema change is introduced by this feature** — the fields already exist on `app/models/schema.py:101-103`. This contract exists so the wizard's client code and any future API consumers know exactly what values are legal and how they map to render behavior.

A `GET /api/v1/bgm/tracks` endpoint contract is also documented here because the wizard needs to enumerate the bundled tracks before the creator can pick one.

---

## `VideoParams.bgm_*` fields — wire shape

Inside the `/api/v1/videos` request body (or anywhere `VideoParams` flows), the music configuration is expressed as three top-level fields:

```json
{
  "video_subject": "...",
  "mode": "short",
  "bgm_type": "file",
  "bgm_file": "storage/uploads/4f9c7e3a-2b1d-4a8f-9e0b-3c5d8e7f6a4b.mp3",
  "bgm_volume": 0.4
}
```

### Field-level contract

| Field | Type | Required when | Constraint | Default (Pydantic) |
|---|---|---|---|---|
| `bgm_type` | string | never (defaults if omitted) | one of: `"random"`, `"file"`, `""` | `"random"` |
| `bgm_file` | string | when `bgm_type == "file"` (else MAY be omitted or `""`) | non-empty path string the engine can resolve | `""` |
| `bgm_volume` | float | never (defaults if omitted) | `0.0 ≤ x ≤ 1.0`, two-decimal precision | `0.2` |

### Three valid wizard configurations

The wizard's three music modes map to these payloads:

#### 1. Preset / Random

```json
{
  "bgm_type": "random",
  "bgm_volume": 0.2
}
```

(`bgm_file` MAY be omitted or sent as `""`.)

The engine picks a random file from `resource/songs/` at render time via `get_bgm_file(bgm_type="random")`.

#### 2. Preset / Specific bundled track

```json
{
  "bgm_type": "file",
  "bgm_file": "resource/songs/output042.mp3",
  "bgm_volume": 0.2
}
```

The engine reads exactly that file. `bgm_type == "file"` because the engine resolver checks for a non-empty `bgm_file` regardless of `bgm_type`, but the wizard sends `"file"` for clarity.

#### 3. Custom upload

```json
{
  "bgm_type": "file",
  "bgm_file": "storage/uploads/4f9c7e3a-2b1d-4a8f-9e0b-3c5d8e7f6a4b.mp3",
  "bgm_volume": 0.4
}
```

The engine reads the uploaded file from `storage/uploads/`.

#### 4. None (voiceover-only)

```json
{
  "bgm_type": ""
}
```

The engine's `get_bgm_file()` short-circuits on empty `bgm_type` and returns no BGM clip — the audio mix step skips entirely.

### Conditional emission rule

The wizard's `/api/generate` proxy MUST NOT include `bgm_*` fields in the request body when the creator never opened the Music panel — see [research.md R4](../research.md). The omitted fields fall through to MPT's Pydantic defaults (`bgm_type = "random"`, `bgm_file = ""`, `bgm_volume = 0.2`), exactly today's behavior. This guarantees byte-equivalence (FR-010, SC-007).

### Forward-compatibility

| v2 extension | How v1 contract accommodates |
|---|---|
| Brand Library music asset references | `bgm_file` is a free-form path string. v1 paths point at `storage/uploads/` or `resource/songs/`; v2 paths point at `brand-library/<tenant>/music/<asset>.<ext>`. No contract change. |
| Multi-track music (intro / main / outro) | Future `bgm_tracks: list[...]` field on `VideoParams`. Existing v1 `bgm_*` fields stay valid; the engine prefers `bgm_tracks` when present. |
| Loudness automation | New optional `bgm_loudness_target_lufs: float` field. v1 senders never include it; existing behavior unchanged. |
| Fade-in / explicit fade-out duration | New optional `bgm_fade_in_seconds` / `bgm_fade_out_seconds` fields. v1 ships with fade-out hardcoded at 3 s in the upstream pipeline. |

---

## `GET /api/v1/bgm/tracks` — bundled track enumeration

A new endpoint that returns the list of bundled BGM tracks the wizard can offer in the Preset dropdown.

### Endpoint

```
GET /api/v1/bgm/tracks
```

### Authentication

Same as the upload endpoint — none at v1.

### Success response

**Status**: 200 OK
**Body**:

```json
{
  "tracks": [
    {
      "name": "output000",
      "path": "resource/songs/output000.mp3",
      "duration_seconds": 102.5
    },
    {
      "name": "output001",
      "path": "resource/songs/output001.mp3",
      "duration_seconds": 87.3
    },
    ...
  ],
  "count": 29
}
```

| Field | Type | Notes |
|---|---|---|
| `tracks[].name` | string | Filename without extension. Used as the dropdown label. v2 may swap to curated human-readable titles. |
| `tracks[].path` | string | Path string the wizard sends as `bgm_file`. Always under `resource/songs/`. |
| `tracks[].duration_seconds` | float | ffprobe-extracted duration. The wizard uses this for the loop/truncate hint when a creator picks a specific track. |
| `count` | integer | Total tracks. Helps the wizard render "29 tracks available" or similar. |

### Behavior

- Reads the directory listing of `resource/songs/` at request time (no caching at v1 — the dir is small, ffprobe is fast).
- Includes only `.mp3` files (the bundled set is all MP3 today). If `.wav`/`.ogg`/`.m4a` files appear in `resource/songs/` later, the endpoint includes them.
- Sorts alphabetically by filename for deterministic dropdown order.

### Performance

The endpoint runs ffprobe once per file to populate `duration_seconds`. With 29 files this takes ~50–100 ms total — acceptable for a Step 3 mount-time fetch. If the bundled set grows past ~200 tracks, the endpoint MUST cache durations (e.g., in a JSON sidecar at `resource/songs/durations.json` regenerated when files change).

### Error responses

| HTTP | Trigger | Body |
|---|---|---|
| 500 | `resource/songs/` directory missing or unreadable | `{"detail": "BGM library unavailable", "error_code": "library_missing"}` |

This shouldn't happen in a deployed instance (the directory is part of the repo / Docker image), but defensive error handling avoids hangs.

### Frontend usage

The wizard's Step 3 fetches `/api/v1/bgm/tracks` once on mount via a frontend proxy at `/api/bgm-tracks` (mirrors the upload proxy pattern). Result is cached in React state for the duration of the wizard session.

---

## Verification (drives task design)

| Test ID | Setup | Expected |
|---|---|---|
| MC-1 | POST `/api/v1/videos` with no `bgm_*` fields | Pydantic validates; render uses `bgm_type="random"`, `bgm_file=""`, `bgm_volume=0.2`. Byte-equivalent to today (SC-007). |
| MC-2 | POST with `bgm_type="random"`, `bgm_volume=0.2` | Pydantic validates; render plays a random bundled track. |
| MC-3 | POST with `bgm_type="file"`, `bgm_file="resource/songs/output005.mp3"`, `bgm_volume=0.5` | Renders with that specific track at 50 % volume. |
| MC-4 | POST with `bgm_type="file"`, `bgm_file="storage/uploads/<uuid>.mp3"`, `bgm_volume=0.3` | Renders with the uploaded track. |
| MC-5 | POST with `bgm_type=""` | Renders voiceover-only; no BGM mix. |
| MC-6 | POST with `bgm_volume=1.5` (out of range) | Pydantic accepts loosely (field is `Optional[float]`); engine clamps or runs at 1.5× amplitude. **Wizard MUST clamp before submission per the data-model invariant** — but the endpoint itself doesn't enforce. |
| MC-7 | POST with `bgm_file="brand-library/tenant_abc/music/intro_v3.mp3"` (future Brand Library path) | Pydantic validates the field shape. Render fails because the path doesn't exist on disk, but the schema accepts it (SC-006 forward-compat). |
| MC-8 | GET `/api/v1/bgm/tracks` | Returns 29 entries (or whatever the bundled set's current count is) sorted alphabetically. |

These eight tests are the contract surface for `/speckit-tasks` to schedule alongside the eight upload-endpoint tests in [audio-upload-endpoint.md](./audio-upload-endpoint.md).
