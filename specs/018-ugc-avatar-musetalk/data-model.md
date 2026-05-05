# Phase 1 Data Model — Mode 4 (UGC Avatar Generator)

**Feature**: 018-ugc-avatar-musetalk
**Date**: 2026-05-05

Mode 4 introduces three logical entities. Per Q2=C resolution, **none require database schema additions in v1** — all entities are filesystem-backed (existing pattern from Mode 2/3/5 outputs). A real Brand-Library data model is deferred to a future spec.

---

## Entity 1 — Speaker Reference

The user's uploaded selfie video that serves as the face-and-body reference for lip-sync.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `tenant_id` | string | yes | Tenant scoping. Encoded in the storage path (`uploads/<tenant>/avatars/...`). |
| `user_id` | string | yes | Uploader identity (logged + retained in metadata sidecar). |
| `slot` | int (1\|2\|3) | yes | One of three retention slots per FR-014's hybrid last-3 model. Stable identifier for the file location. |
| `uuid` | string (12 hex chars) | yes | Random per-upload identifier. Filename body. Lets the wizard refer to a specific selfie even after a slot rotation. |
| `path` | string | yes | Absolute filesystem path under L3 storage: `storage/uploads/<tenant>/avatars/slot{N}/<uuid>.mp4`. |
| `mime_type` | string | yes | One of: `video/mp4`, `video/quicktime`, `video/webm`. Validated at upload time. |
| `duration_seconds` | float | yes | Probed via FFprobe at upload. Validated 5.0 ≤ duration ≤ 60.0 (we accept up to 60s in case the user uploads a longer take, but only the first 15s are used as the reference). |
| `face_bbox` | object | yes | Detected face bounding box: `{x: int, y: int, w: int, h: int, confidence: float}`. Surfaced to the wizard for the "we picked this face — was that right?" UX. |
| `face_count_detected` | int | yes | Total faces seen. > 1 triggers the multi-face warning. |
| `created_at` | ISO datetime | yes | mtime of the file. Used for last-3 eviction. |
| `width`, `height` | int | yes | Source dimensions. Informational. |

### Storage layout

```text
storage/uploads/<tenant_id>/avatars/
├── slot1/
│   ├── <uuid>.mp4
│   └── <uuid>.meta.json    # serialized fields above except `path` (which is implicit)
├── slot2/
│   ├── <uuid>.mp4
│   └── <uuid>.meta.json
└── slot3/
    ├── <uuid>.mp4
    └── <uuid>.meta.json
```

### Validation rules

1. **Format**: MP4 (`.mp4`), QuickTime (`.mov`), or WebM (`.webm`). Any other MIME type → 400.
2. **File size**: ≤ 100 MB. Larger uploads rejected with `413 payload_too_large`.
3. **Duration**: 5.0 ≤ duration ≤ 60.0 seconds. Out-of-band → 400 `duration_out_of_range`.
4. **Face**: at least one face must be detected with confidence ≥ 0.7. Otherwise 400 `no_face_detected`.
5. **Frame rate**: ≥ 24 fps. Lower fps would make lip-sync stuttery. Otherwise 400 `frame_rate_too_low`.
6. **Resolution**: shortest side ≥ 480 px. Otherwise 400 `resolution_too_low`.

### Lifecycle / state transitions

```text
                       upload validated
   (no record) ───────────────────────────► occupied
                                             │
                                             │  4th upload arrives
                                             │  → oldest slot evicted from disk
                                             ▼
                                       freed (slot reused)
```

No "active vs archived" state; selfies are simply present-or-evicted.

---

## Entity 2 — Avatar Render

A single Mode-4 generation request. Identical conceptual shape to Mode 2's render task — extends with `speaker_reference_path`.

### Fields (extension of existing `VideoParams`)

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | Literal | yes | New value: `"ugc_avatar"`. Added to the `Mode` literal in `app/models/schema.py`. |
| `speaker_reference_path` | string | yes | Absolute path or pre-signed URL of the chosen Speaker Reference (Entity 1). L1 wizard sends this; L3 reads the file directly when local, fetches when pre-signed. |
| `voice_name` | string | yes | Edge TTS voice id (existing field). Drives both audio synthesis AND script-language inference per FR-005. |
| `video_subject` | string | yes | Topic / brief (Auto mode), pasted script (Verbatim/Polish modes). Existing field. |
| `video_script` | string | conditional | Required for Verbatim/Polish; empty for Auto. Existing. |
| `script_mode` | Literal | yes | One of `"auto"`, `"verbatim"`, `"polish"`. Existing. |
| `video_aspect` | Literal | yes | Always `"9:16"` for Mode 4 (portrait). Existing field; mode registry pins it. |
| `video_clip_duration` × `video_count` | int × int | yes | Together describe target output duration. Effective duration = `clip_duration * count`. Cap at 300s per FR-013. |
| `tenant_id`, `user_id` | string | yes | Multi-tenant context (Constitution Principle III). Existing fields. |

**Fields explicitly NOT used by Mode 4** (set to None / empty / null at dispatch):

- `pre_signed_clip_urls` — Mode 4 has no per-segment B-roll.
- `segments` — same reason.
- `visuals_mode` — Mode 4's visuals are entirely the speaker reference.
- `uploaded_product_paths`, `uploaded_model_path` — these are spec 006 fields for Mode 1/2 product imagery; not applicable.

### Pipeline state machine

```text
queued
   │  L3 controller received the request
   ▼
selfie_resolved
   │  speaker_reference_path validated; face crop bounding box ready
   ▼
audio_synthesized
   │  TTS audio MP3 written to storage/tasks/<task_id>/audio.mp3
   ▼
visuals_extended (CONDITIONAL)
   │  if (audio_duration > selfie_duration), ping-pong-extend the speaker
   │  reference to match audio_duration; output to extended_reference.mp4
   ▼
lip_synced
   │  MuseTalk inference complete; output written to lipsync.mp4
   │  (face region replaced with mouth-synced version, body unchanged)
   ▼
subtitled
   │  subtitle.srt generated from audio; burned in via FFmpeg with
   │  GeezaPro font auto-swap if narration is Arabic
   ▼
complete
   │  final-1.mp4 published to storage/tasks/<task_id>/final-1.mp4
   ▼
done
```

Failure transitions: any step → `failed` with a typed error code (FR-011). Errors logged with `tenant_id` + `user_id` + `generation_id`.

---

## Entity 3 — Avatar Asset

The final output. Same shape as Mode 2/3/5 outputs — no special schema.

### Fields

| Field | Type | Description |
|---|---|---|
| `task_id` | string (UUID4) | Existing render-task identifier. |
| `output_path` | string | `storage/tasks/<task_id>/final-1.mp4`. |
| `subtitle_path` | string | `storage/tasks/<task_id>/subtitle.srt`. |
| `duration_seconds` | float | Probed from final-1.mp4. |
| `voice_name` | string | Voice that was used (informational). |
| `language` | string | Inferred from voice_name (e.g. `"Arabic (Egyptian dialect)"`). |
| `script_text` | string | The narration that was spoken. |
| `speaker_reference_uuid` | string | UUID of the Speaker Reference used. Lets the My Assets surface group renders by source selfie. |
| `created_at` | ISO datetime | mtime of final-1.mp4. |

Persisted alongside other modes' assets in the existing `My Assets` history surface — no new UI for v1.

---

## Relationships

```text
Speaker Reference (1) ────────────► (N) Avatar Render
                  belongs to            ─────► one selfie per render

Avatar Render (1) ───────► (1) Avatar Asset
                  produces

Tenant (1) ────────► (N) Speaker Reference
                ───► (N) Avatar Render / Asset
       multi-tenant scoping
       (no cross-tenant access)
```

A Speaker Reference can be used by many Avatar Renders (the picker in the wizard surfaces the last-3 references). Each Avatar Render produces exactly one Avatar Asset on success or zero on failure.

---

## Data NOT modeled in v1

Per the spec's scope-bound list and Q2=C resolution, the following are deliberately deferred:

- **Persistent named avatars** (e.g. "My happy avatar", "My serious avatar"). v1 has slot-numbered last-3 only.
- **Cross-tenant shared avatars** (agency model serving multiple end-clients).
- **Avatar versioning** (track changes over time).
- **Liveness / consent metadata** (was the selfie consensual? is it the actual user?).
- **Brand-bound default avatars** (per-product / per-campaign defaults).

These are spec-out-of-scope and would land as separate features.
