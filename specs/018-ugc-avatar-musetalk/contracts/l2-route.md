# Contract — L2 Mode 4 Orchestrator

**Surface**: L2 (orchestration). The existing `POST /api/v1/videos` endpoint gains a third orchestrator branch (alongside `mode="short"` and `mode="faceless"` shipped in spec 017) for `mode="ugc_avatar"`.

## Behavior

### Existing dispatcher in `app/routes/videos.py`

```python
def _should_orchestrate(body) -> str | None:
    """Returns 'short' | 'faceless' | 'ugc_avatar' or None for passthrough."""
```

Mode 4 follows the same eligibility gate as Mode 2/5:
- `mode == "ugc_avatar"`
- `script_mode` is unset, empty, or `"auto"` (Auto/Polish/Verbatim handled differently — see below)
- `video_subject` non-empty
- `speaker_reference_path` provided

### Pre-orchestrator validation (L2 only)

Before calling any helper:
1. **`speaker_reference_path` required**: missing → 400 `speaker_reference_required`. Mode 4 cannot proceed without one.
2. **Selfie file accessible**: the path must resolve to a real file (HEAD-checked or filesystem-checked depending on whether the path is a pre-signed URL or local).
3. **Duration cap**: if `video_clip_duration * video_count > 300`, clamp to 300 with a warning logged.

### Orchestrator path — Auto mode

Mirror of Mode 2's flow:
1. Infer language from `voice_name` (existing helper `voice_helpers.infer_language_from_voice`).
2. Call `marketing_script.generate_marketing_script(subject, duration_seconds, language)` (existing — Mode 4 reuses Mode 2's helper per research.md R4).
3. **Skip** `visual_relevance` — Mode 4 has no per-segment B-roll. Also skip the segments[] field entirely.
4. Augment the body with `video_script=full_text`, `script_mode="verbatim"` (so L3 doesn't re-generate).
5. Forward augmented body to L3 `/api/v1/videos`.

### Orchestrator path — Verbatim / Polish

Verbatim and Polish bypass L2's script generation; the user's script is in `body.video_script` already. L2's job is reduced to:
1. Validate `speaker_reference_path` (above).
2. Forward the request unchanged to L3 (L3's mode-registry pipeline handles polish-mode internally per spec 013).

### Passthrough fallback

Any unmet eligibility (e.g., `script_mode="verbatim"` with no script provided, or `mode != "ugc_avatar"`) → forward as-is, like the existing forwarder behavior. L3 returns its own error if invalid.

## Request — example (Auto mode, Arabic voice)

L1 → L2:

```http
POST /api/v1/videos HTTP/1.1
Host: 127.0.0.1:8089
Authorization: Bearer demo-bearer-replace-in-production
Content-Type: application/json

{
  "video_subject": "Caffeine-free organic energy drink for working parents",
  "video_script": "",
  "mode": "ugc_avatar",
  "video_aspect": "9:16",
  "video_concat_mode": "sequential",
  "video_transition_mode": "FadeIn",
  "video_clip_duration": 5,
  "video_count": 6,
  "voice_name": "ar-EG-SalmaNeural-Female",
  "video_language": "",
  "paragraph_number": 1,
  "script_mode": "auto",
  "speaker_reference_path": "storage/uploads/demo-tenant-001/avatars/slot2/a3f9d6e2c1b8.mp4"
}
```

After L2 augmentation, what L3 receives:

```http
POST /api/v1/videos HTTP/1.1
Host: 127.0.0.1:8090
Authorization: Bearer demo-bearer-replace-in-production
Content-Type: application/json

{
  "video_subject": "Caffeine-free organic energy drink for working parents",
  "video_script": "هل تحتاج إلى طاقة سريعة دون قلق...",   // Egyptian Arabic Hook→Body→CTA
  "mode": "ugc_avatar",
  "video_aspect": "9:16",
  "video_concat_mode": "sequential",
  "video_transition_mode": "FadeIn",
  "video_clip_duration": 5,
  "video_count": 6,
  "voice_name": "ar-EG-SalmaNeural-Female",
  "video_language": "",
  "paragraph_number": 1,
  "script_mode": "verbatim",                            // upgraded by L2
  "speaker_reference_path": "storage/uploads/demo-tenant-001/avatars/slot2/a3f9d6e2c1b8.mp4"
}
```

## Response

L2 forwards L3's response unchanged (existing pattern). Returns the L3 task id:

```json
{
  "status": 200,
  "message": "success",
  "data": {
    "task_id": "8a2f9c4e-1d6b-7890-abcd-1234567890ef"
  }
}
```

## Failure modes

| Trigger | HTTP | error_code |
|---|---|---|
| `speaker_reference_path` missing for `mode=ugc_avatar` | 400 | `speaker_reference_required` |
| Selfie file not accessible at L2-resolution time | 400 | `speaker_reference_not_found` |
| `video_subject` empty AND `script_mode != "verbatim"` | 400 | `video_subject_required` |
| `marketing_script` returns empty `full_text` | — | falls through to passthrough; L3 generates its own script via `mode_impl.generate_script` |
| L3 5xx during dispatch | bubbled | L3's error verbatim |

## Polling — wizard side

L1 wizard polls existing `GET /api/status/{task_id}` (proxied through L2 → L3) every 4 seconds. Mode 4 task progress passes through the same shape as Mode 2.

Stage labels surfaced in progress updates:
1. `"Validating selfie"` — face detect + format check (typically < 1s; happens at upload time, before render dispatch)
2. `"Generating script"` — Auto/Polish only
3. `"Synthesizing voice"` — Edge TTS
4. `"Extending visuals"` — only when audio > selfie duration; ping-pong loop step
5. `"Lip-syncing"` — MuseTalk inference. Longest stage; minutes for 5-min videos.
6. `"Adding subtitles"` — burn-in via FFmpeg
7. `"Finalizing"` — encode final-1.mp4
