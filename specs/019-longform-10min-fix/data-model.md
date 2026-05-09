# Data Model: Mode 3 long-form 10-minute cap + URL-expiry resilience + WebM selfie uploads

**Feature**: `019-longform-10min-fix` | **Date**: 2026-05-09

This feature does not introduce new persisted entities. It modifies behavior around three existing in-flight artifacts. Each is documented below as an "operational entity" — a thing the rendering pipeline operates on, with its lifecycle, validation rules, and state transitions.

## Entity: PreSignedClipUrl

A single-use download URL that L2 (orchestration) mints for L3 to fetch. Carries a render-pipeline clip artifact.

| Field | Type | Constraint / Source | Notes |
|---|---|---|---|
| `url` | string (URL) | Issued by L2 | Includes signature and `Expires=` query param (S3-compatible). |
| `target_duration_seconds` | float | Out-of-band metadata from L2 | Used by L3 to size a black-frame placeholder if the URL is unfetchable. |
| `clip_index` | int (1..N) | Position in render's clip list | Preserved through the placeholder-substitution path (FR-008). |

**Lifecycle / state transitions**:

```
[issued by L2]
    │
    ▼
  valid ─────────► fetched ─────► stored as real clip
    │
    ├─► 5xx (transient) ─► retry once with 2s backoff ─► fetched | dead
    │
    └─► 403 / 410 ─► dead (FR-004, no retry)
                       │
                       ▼
                placeholder substituted (FR-005)
```

**Validation rules** (per FR-003, FR-004, FR-007):
- Status 403 → terminal, no retry.
- Status 410 → terminal, no retry.
- Status ≥ 500 → at most one retry after 2s.
- Status timeout / connection error → at most one retry after 2s.
- Any other dead state after retry budget → trigger placeholder substitution; do not raise.

## Entity: BlackFramePlaceholderClip

A locally-generated MP4 written in place of an unfetchable real clip.

| Field | Type | Value | Notes |
|---|---|---|---|
| `path` | filesystem path | `storage/tasks/<task_id>/clips/clip-<i>.mp4` | Same naming pattern as a real clip — assembly step is unaware of the substitution. |
| `width` | int | 1280 | Per Decision 1 (research.md). |
| `height` | int | 720 | Per Decision 1. |
| `framerate` | int | 30 | Matches project's render fps. |
| `duration_seconds` | float | inherited from `PreSignedClipUrl.target_duration_seconds`, or `5.0` default | Default applies when target duration is unknown to the fetch step (edge case in spec). |
| `pixel_format` | string | `yuv420p` | Consumer-device compatible. |
| `audio` | none | `-an` flag at encode time | No audio track (Decision 1, research.md). |
| `codec` | string | `libx264 (veryfast preset)` | Per Decision 1. |

**Lifecycle**: written once, read once by the assembly step, deleted with the rest of the per-task working dir at the end of the render. Not persisted beyond the task.

**Validation rules** (per FR-004, FR-006):
- Path MUST exist after the encode step. If FFmpeg fails to write it, the render fails with `material.fetch_failed` (FR-006).
- File MUST be a valid MP4 readable by the MoviePy/FFmpeg-based assembly step (FR-004).
- Duration MUST equal the `target_duration_seconds` of the failed URL (or the 5.0s default) within ±0.05s.

**Logging contract** (per FR-005):
- Each placeholder substitution emits a `WARNING`-level log line including: clip index, original URL (truncated to 80 chars), the underlying fetch error string. This line is the audit trail; downstream layers can grep for it to compute per-render placeholder ratios.

## Entity: SpeakerReference (upload variant)

A creator-uploaded selfie video destined to become a Mode 4 speaker reference.

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `request.content_type` | string | RFC 7231 §3.1.1.1 format | May contain a parameter list, e.g. `video/webm;codecs=vp8`. |
| `mime_lookup_key` | string | `request.content_type.split(";", 1)[0].strip().lower()` | Computed; FR-008. Used for accept-list lookup. |
| `accepted_mimes` | enum | `{ video/mp4, video/quicktime, video/webm, video/x-matroska }` | Allow-list keyed by the stripped lookup form. |
| `body_bytes` | bytes | ≤ ~50 MB cap (existing) | Cap is unchanged by this feature. |
| `tenant_id` | string | from JWT or demo default `demo-tenant-001` | Constitution §III propagation. |
| `user_id` | string | from JWT or demo default `demo-user-001` | Constitution §III propagation. |
| `slot_index` | int (1..3) | Hybrid persistence per spec 018 FR-014 | Unchanged by this feature. |

**Lifecycle / state transitions**:

```
[upload arrives]
    │
    ▼
strip codec params from content-type (FR-008)
    │
    ├─► not in accept-list ─► reject 400 with original content-type echoed (FR-010)
    │
    ▼
allowed: ext is .mp4 / .mov / .webm / .mkv
    │
    ├─► .mp4 ─► move into place (no transcode)
    │
    ├─► .mov ─► move into place (existing path; no change)
    │
    └─► .webm | .mkv ─► re-encode video to H.264 yuv420p, drop audio (FR-009)
                            │
                            ▼
                        persisted as <slot>.mp4
```

**Validation rules** (per FR-008, FR-009, FR-010):
- The accept-list lookup MUST use the parameter-stripped MIME — `video/webm;codecs=vp8` and `video/webm` MUST hit the same entry.
- WebM and MKV uploads MUST be re-encoded; stream-copy is forbidden because VP8/VP9 cannot be muxed into MP4.
- The error payload for an unsupported MIME MUST include the **original** unmodified `Content-Type` string the client sent (FR-010), not the parameter-stripped form, so the creator can debug their client.
- All other validation downstream of MIME (face-detect via MediaPipe per spec 018, duration band 5–60s, fps ≥ 24, short-side ≥ 480px) is unchanged — this feature is exclusively about the MIME-handling and persist steps.

## Cross-entity invariants

- **Tenant context** (Constitution §III): every operation on `BlackFramePlaceholderClip` happens inside a tenant-tagged render task; the working directory naming preserves provenance. Every operation on `SpeakerReference (upload variant)` runs inside a request handler that has a JWT (or demo defaults) at the top of its scope. Neither entity introduces a code path where tenant context is dropped.
- **No external API call** (Constitution §IV): both new code paths (`_write_black_frame_clip`, the WebM re-encode in `upload_selfie`) invoke local FFmpeg only.
- **No new mode** (Constitution §V): Mode 3's registry entry mutates in value (duration choices, segment count range); the registry shape is unchanged. Mode 4's selfie path is plumbing for an already-declared mode. No constitution amendment required.
