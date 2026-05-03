# Contract — Layer 2 `/api/v1/long-form-videos`

**Layer**: Orchestration (Layer 2 — `visualai-orchestration` repo)
**Step**: 3 (demo-tenant single-user); spec 014 lifts to multi-tenant.
**Created**: 2026-05-03

All endpoints require `Authorization: Bearer <LAYER2_DEMO_BEARER>` header. Missing or wrong bearer ⇒ HTTP 401, body `{"detail":{"error_code":"invalid_bearer","detail":"..."}}`.

---

## POST `/api/v1/long-form-videos`

Create a new long-form video generation. Synchronous: returns when the video is fully assembled (~3–5 minutes wall-clock for a 3-minute target).

### Request — `application/json`

```json
{
  "source_type": "topic" | "url" | "script",
  "source_text": "string (≤500 chars for topic, ≤1500 words for script, valid URL for url)",
  "target_duration_seconds": 120 | 180 | 240 | 300,
  "voice_id": "en-US-AvaMultilingualNeural",
  "music_id": "output007.mp3"
}
```

`music_id` may be `null` for silent (no BGM); omitted ⇒ defaults to `null`.

### Responses

**200 OK** — generation complete. Body matches `LongFormGeneration` from `data-model.md`.

```json
{
  "id": "lf_a1b2c3d4e5f6",
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "status": "complete",
  "source_type": "topic",
  "source_text": "How AI is changing logistics in 2026",
  "target_duration_seconds": 180,
  "actual_duration_seconds": 178.4,
  "voice_id": "en-US-AvaMultilingualNeural",
  "music_id": "output007.mp3",
  "script_text": "...full narration...",
  "output_video_url": "https://layer2.example/_signed/...",
  "subtitle_band_y_pct": 0.80,
  "latency_ms": 215000,
  "cost_estimate_usd": 0.18,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-05-03T18:00:00Z",
  "completed_at": "2026-05-03T18:03:35Z"
}
```

**422 Unprocessable Entity** — request validation failed.

```json
{ "detail": { "error_code": "<see table>", "detail": "..." } }
```

| `error_code` | Trigger |
|---|---|
| `source_too_long` | topic > 500 chars OR script > 1500 words |
| `source_too_short` | empty `source_text` after trim |
| `invalid_target_duration` | `target_duration_seconds` not in {120,180,240,300} |
| `unknown_voice_id` | `voice_id` absent from voice catalog |
| `unknown_music_id` | `music_id` absent from `resource/songs/` |
| `invalid_url` | `source_type == "url"` and URL regex fails |

**502 Bad Gateway** — Layer 3 render failed or Layer 2.5 visual provider failed.

```json
{ "detail": { "error_code": "assembly_failed" | "script_generation_failed" | "voice_synthesis_failed", "detail": "..." } }
```

**504 Gateway Timeout** — generation exceeded 10 minutes (FR-019).

```json
{ "detail": { "error_code": "provider_timeout", "detail": "..." } }
```

---

## GET `/api/v1/long-form-videos`

List all long-form generations for the demo tenant, newest-first. Output URLs are re-minted on read.

### Response — 200 OK

```json
[
  { /* LongFormGeneration */ },
  { /* LongFormGeneration */ }
]
```

Records whose `final-1.mp4` is missing or below 100KB are filtered out (mirrors spec 015's empty-shot filter). Default cap of 100 records; pagination is a Step-4 add.

---

## GET `/api/v1/long-form-videos/{id}`

Fetch a single record. Output URL re-minted.

### Responses

- **200 OK** — body matches `LongFormGeneration`.
- **404 Not Found** — `{"detail":{"error_code":"not_found","detail":"no record lf_..."}}`.

---

## Idempotency + concurrency

POST is **not** idempotent — duplicate calls produce distinct records. v1 ships sequential generation per user; concurrent POSTs are served sequentially by the FastAPI worker. Spec 014 will revisit per-tenant rate limits.

## Logging

Every request logs `tenant_id`, `user_id`, `generation_id`, and the inbound `source_type` via loguru (Constitution §Technology Constraints — Observability).
