# Contract: Layer 3 `/api/v1/videos` HTTP API (extended)

**Feature**: 002-video-duration-variations
**Layer**: 3 — Rendering Engine (this repository)
**Owner**: this repository; served by [app/controllers/v1/video.py](../../../app/controllers/v1/video.py)
**Consumer**: Layer 2 Orchestration API (future) OR Layer 1 frontend direct (Step 1 only, temporary)

This contract extends the existing `/api/v1/videos` endpoint. Pre-existing fields (e.g., `video_subject`, `voice_name`, subtitle styling) remain unchanged and are omitted from this document.

---

## Endpoint: `POST /api/v1/videos`

### Request body (new / changed fields only)

```jsonc
{
  "video_subject": "organic skincare for sensitive skin",

  // NEW — required
  "total_duration_seconds": 60,         // int, 5 ≤ x ≤ 90

  // NEW — optional
  "variation_count": 3,                 // int, 1 ≤ x ≤ 3, default 1
  "render_mode": "preview",             // "preview" | "full", default "full"
  "seed": 4217,                         // int, default: random (server logs the seed)

  // DEPRECATED with this feature (kept for backwards compat through Step 2):
  //   "video_count": 1
}
```

### Validation (Pydantic rules on `VideoParams`)

| Field | Rule | Error (HTTP 422) |
|---|---|---|
| `total_duration_seconds` | `Field(ge=5, le=90)` | `"total_duration_seconds must be between 5 and 90"` |
| `variation_count` | `Field(ge=1, le=3)` | `"variation_count must be between 1 and 3"` |
| `render_mode` | `Literal["preview", "full"]` | `"render_mode must be 'preview' or 'full'"` |
| `seed` | `int` (any 32-bit value accepted) | n/a |

### Response

```json
{
  "task_id": "c0ffee11-...",
  "status": "queued",
  "variation_index": 0,
  "render_mode": "preview"
}
```

One task per variation per render_mode call. Layer 2 (or the Step-1 frontend) issues N parallel calls, one per variation, incrementing `seed` by 1 per call to produce the `seed_base + i` pattern.

### Behavior matrix

| `render_mode` | `total_duration_seconds` | Behavior |
|---|---|---|
| `preview` | any | Produce a 5-second MP4. Final assembly truncates at t=5s. All upstream pipeline stages still run but may short-circuit when deterministic. Produced file uses the literal first-5s of what a full render would produce for the same `seed` + inputs. |
| `full` | ≤ 30 | Produce a full-length MP4. No preview gate. Returns when render completes. |
| `full` | > 30 | Produce a full-length MP4. This repo does NOT enforce an approval gate — callers (Layer 2) are responsible for only calling `render_mode=full` after the preview was approved. Layer 3 will honor the request either way. |

### Determinism guarantee

For identical `(video_subject, video_script, voice_name, bgm_type, seed, <all other inputs>)`:
1. `render_mode=preview` produces an MP4 whose bytes are exactly the first 5 seconds of the MP4 produced by `render_mode=full` (codec keyframe alignment permitting ≤ 40 ms offset).
2. Two repeated calls with the same inputs and `seed` produce byte-identical output.

This guarantee is the regression target for SC-005 (perceptual similarity ≥ 90 %).

---

## Endpoint: `GET /api/v1/videos/{task_id}`

Existing endpoint, response shape extended:

```json
{
  "task_id": "c0ffee11-...",
  "status": "queued | rendering | complete | failed",
  "stage": "script | voice | material | assembly | complete",
  "progress": 0.42,
  "render_mode": "preview",
  "variation_index": 0,
  "asset_url": null,
  "error": null,
  "tenant_id": "t_...",
  "user_id": "u_..."
}
```

(`tenant_id` / `user_id` fields populated from Step 2 onward; null in Step 1 single-tenant mode.)

---

## Redis events (emitted by Layer 3)

Layer 3 publishes state transitions to Redis so Layer 2 can trigger credit-ledger updates without polling.

| Channel | Payload | When |
|---|---|---|
| `mpt:task:{task_id}:preview_ready` | `{"variation_index": 0, "asset_url": "..."}` | After a preview render completes successfully |
| `mpt:task:{task_id}:full_ready` | `{"variation_index": 0, "asset_url": "..."}` | After a full render completes successfully |
| `mpt:task:{task_id}:failed` | `{"variation_index": 0, "error": "..."}` | On any render failure |

No credit-ledger fields in these events. Credits are never Layer 3's concern.

---

## Error semantics

| Condition | HTTP | Behavior |
|---|---|---|
| Pydantic validation failure | 422 | Return field-level error list. No task created. |
| GPU / external provider failure mid-render | 202 then `failed` | Task accepts, transitions to `failed`, emits Redis `failed` event. Layer 2 retries up to 2 times free per spec's edge-case rule; further retries are paid. |
| `render_mode=preview` on `total_duration_seconds ≤ 30` | 200 | Honored; produces a 5-s MP4 even though the caller didn't need the gate. No enforcement in Layer 3. |
| Seed collision detected during render (variations collapse to identical output) | 200 | Not detected by Layer 3; detection is a Layer 2 concern (compare content hashes after all N previews complete). |

---

## Backwards compatibility

Step 1 callers (the existing Streamlit WebUI and early Next.js frontend) may omit the new fields entirely. Defaults apply:
- `total_duration_seconds`: if absent, fall back to LLM-derived length (Step 1 temporary; controlled by a server-side feature flag `REQUIRE_EXPLICIT_DURATION=false` during Step 1, `true` from Step 2 onward).
- `variation_count`: default 1 matches existing `video_count` behavior.
- `render_mode`: default `full` matches existing behavior.
- `seed`: default random matches existing behavior; server logs the chosen seed for reproducibility.

The `video_count` field is deprecated and slated for removal in the Step 3 milestone (concurrent with the `material.py` rewrite). Until then, `video_count > 1` produces N independent renders without variation-diversity logic applied; prefer `variation_count` going forward.
