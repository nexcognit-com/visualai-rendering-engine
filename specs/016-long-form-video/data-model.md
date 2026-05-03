# Data Model — Mode 3 Long-Form Video Generator

**Phase**: 1 (entities + state transitions + validation)
**Created**: 2026-05-03

## Overview

One persisted entity (`LongFormGeneration`) and one internal-only entity (`ScriptSegment`). Persistence is JSON-file at `storage/tasks/lf_<id>/record.json` in Layer 2 (Step-3 stand-in for the eventual Layer-4 Neon `long_form_generations` table). Same shape; just files for v1.

## Entities

### LongFormGeneration (persisted)

Represents a single user-initiated long-form video generation, end-to-end.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Format `lf_<12-hex>`; collision-safe per UUID-v4 hex prefix. |
| `tenant_id` | string | yes | Demo-tenant in v1; spec 014 closes the multi-tenant debt. |
| `user_id` | string | yes | Demo-user in v1. |
| `status` | enum | yes | `running` \| `complete` \| `failed`. |
| `source_type` | enum | yes | `topic` \| `url` \| `script`. |
| `source_text` | string | yes | The original user input (≤500 chars for `topic`, ≤1500 words for `script`, full URL for `url`). Truncated to 2000 chars for storage. |
| `target_duration_seconds` | int | yes | One of {120, 180, 240, 300}. |
| `actual_duration_seconds` | float | no | Set on completion; absent while `running` or after early `failed`. |
| `voice_id` | string | yes | E.g., `en-US-AvaMultilingualNeural`; matches Mode 2's voice library. |
| `music_id` | string \| null | yes | Bundled BGM filename (`output007.mp3` etc.) or `null` for silent. |
| `script_text` | string | no | Final narrated script; populated once script-gen succeeds. |
| `output_video_url` | string | no | Pre-signed; re-minted on every read (15-min TTL). Absent while `running` or after failure. |
| `subtitle_band_y_pct` | float | yes | `0.80` constant for v1 (set by mode registry). Persisted for forward compatibility. |
| `latency_ms` | int | no | Set on `complete` or `failed`. |
| `cost_estimate_usd` | float | no | Set on `complete`. SC-005 caps median ≤ $0.50. |
| `error_code` | string \| null | no | One of: `script_generation_failed`, `voice_synthesis_failed`, `assembly_failed`, `source_too_long`, `source_too_short`, `url_unreachable`, `provider_timeout`. |
| `error_message` | string \| null | no | Human-readable detail; truncated to 500 chars before persistence. |
| `created_at` | ISO 8601 datetime | yes | UTC. |
| `completed_at` | ISO 8601 datetime | no | UTC. Absent while `running`. |

#### Validation rules

- `source_type == "topic"` ⇒ `len(source_text) ≤ 500`.
- `source_type == "script"` ⇒ word count of `source_text` ≤ 1500.
- `source_type == "url"` ⇒ `source_text` matches a URL regex (`^https?://...`).
- `target_duration_seconds ∈ {120, 180, 240, 300}` (FR-003).
- `voice_id` MUST match an entry in the Mode 2 voice catalog (FR-004).
- `music_id` MUST match an entry in `resource/songs/` or be exactly `null`.
- On `complete`: `output_video_url` MUST be set, `actual_duration_seconds` MUST be within ±15s of `target_duration_seconds` (FR-017, SC-002).
- On `failed`: `error_code` AND `error_message` MUST both be set; `output_video_url` MUST be absent.

#### State transitions

```text
        ┌─────────────┐
   ─────► running     │ (initial state at POST)
        └──────┬──────┘
               │
        ┌──────┴───────┐
        ▼              ▼
  ┌─────────────┐  ┌─────────────┐
  │  complete   │  │   failed    │
  │ (terminal)  │  │ (terminal)  │
  └─────────────┘  └─────────────┘
```

`running → running` is allowed only as a same-state save (e.g., updating `script_text` after script-gen succeeds, before voice synthesis runs). `complete` and `failed` are terminal — no transition out. The store rejects writes that mutate a terminal record's `status`, `error_code`, or `output_video_url` to prevent silent overwrites.

#### Filesystem layout

```text
storage/tasks/lf_<id>/
├── record.json          # the persisted LongFormGeneration
├── script.txt           # final script (also denormalised into record.script_text)
├── voice.mp3            # full-script narration (Layer 3 may store under a different name)
├── final-1.mp4          # the assembled MP4 (Layer 3's existing convention)
└── segments/            # per-segment B-roll cache (debugging only — not user-facing)
    ├── seg-01.jpg
    └── seg-02.jpg
```

Files under `segments/` may be cleaned up post-render — Layer 1 only needs the pre-signed `final-1.mp4`. The list endpoint filters out records where `final-1.mp4` is missing or under 100KB (an extension of spec 015's empty-shot filter; long-form videos at 1080p are tens of MB, so 100KB catches obvious failures while a real video easily clears it).

### ScriptSegment (internal, not exposed via API)

Represents a single contiguous chunk of the produced narration with its own visual + timing. Stored in-memory during a generation; not persisted to `record.json`.

| Field | Type | Notes |
|---|---|---|
| `index` | int | 0-based segment order in the final video. |
| `start_seconds` | float | Wall-clock start in the assembled video. |
| `end_seconds` | float | Wall-clock end. |
| `text` | string | Narrated text for this segment. Determines TTS sub-clip and subtitle band content. |
| `visual_ref` | string | Pre-signed URL OR generation id pointing to the B-roll asset. Unset means "use the previous segment's visual" (rare; ≤ 2 per video). |

#### Validation rules

- `start_seconds < end_seconds`.
- All segments cover `[0, actual_duration_seconds]` with no gaps and no overlaps.
- Total segment count: 8 ≤ N ≤ 25 (≈ 12–25s per segment for a 3-minute video at the lower end, 7–18s at the upper end).

ScriptSegments live in Layer 3 during render; Layer 2 doesn't materialize them. Future-Step optimization: persist segments alongside the record so a partial failure can resume from the last successful segment.

## Cardinality

- `LongFormGeneration` 1 ↔ 0..* `ScriptSegment` (segments are ephemeral; one render run produces them; they don't survive past the render).
- `LongFormGeneration` *..1 `Tenant` (Step-4 — until then, demo-tenant only).

## Relationships to other modes

`LongFormGeneration` is structurally analogous to spec 015's `ProductShootGeneration`: same lifecycle, same persistence pattern, same pre-signed URL refresh policy. Frontend's My Assets page already handles a generic "generation card with thumbnail" — only the variant needed here is "landscape thumbnail + Mode 3 badge".

## Forward-compat notes (Step 4 / Neon)

When the eventual Neon `long_form_generations` table lands:
- All JSON-file fields above map 1:1 to columns.
- `subtitle_band_y_pct` becomes a `numeric(4,2)` column (allows future per-mode override).
- `script_text` migrates to a `text` column with a CHECK constraint on length.
- Foreign keys: `tenant_id`, `user_id`, `voice_id` → respective lookup tables.
- Indexes: `(tenant_id, created_at DESC)` for the list endpoint; `(status)` for the cleanup job.
