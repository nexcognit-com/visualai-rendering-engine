# Quickstart — Mode 4 (UGC Avatar Generator)

**Feature**: 018-ugc-avatar-musetalk
**Date**: 2026-05-05

End-to-end smoke test for Mode 4. Run from a working VisualAI dev environment (L1 + L2 + L3 services already started — see [README](../../README.md)).

## Prerequisites (one-time setup)

```sh
# 1. L3: install MuseTalk + MediaPipe deps
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo
.venv/bin/pip install \
  "git+https://github.com/TMElyralab/MuseTalk@<pinned-sha>" \
  "mediapipe>=0.10" \
  "torch>=2.1"  # MPS support requires 2.1+

# 2. L3: download MuseTalk weights (~2GB)
.venv/bin/python -c "from app.services.lip_sync import _download_weights; _download_weights()"
# Or set MUSETALK_MODEL_DIR to a path with the weights pre-downloaded.

# 3. L3 env vars (in MoneyPrinterTurbo/.env)
echo 'LIP_SYNC_ENGINE=musetalk' >> .env       # or "mock" for dev without GPU/MPS
echo 'MUSETALK_MODEL_DIR=/path/to/weights' >> .env

# 4. Verify the engine loads
.venv/bin/python -c "from app.services.lip_sync import run; print('lip_sync ok')"
```

For Apple Silicon dev (no CUDA), MuseTalk runs on MPS — set `PYTORCH_ENABLE_MPS_FALLBACK=1` in the env to allow ops not yet ported to MPS to fall back to CPU.

## Smoke test 1 — selfie upload

```sh
# 1. Record a 10-second selfie or use any reference video
SELFIE=/path/to/selfie.mp4   # 5-15s; clear face; ≥720p shortest side

# 2. Upload via L2 (which proxies to L3)
curl -s -X POST http://127.0.0.1:8089/api/v1/avatars/upload \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -F "file=@${SELFIE}" | jq

# Expected response:
# {
#   "uuid": "<12 hex>",
#   "tenant_id": "demo-tenant-001",
#   "user_id": "demo-user-001",
#   "slot": 1,
#   "path": "storage/uploads/demo-tenant-001/avatars/slot1/<uuid>.mp4",
#   "duration_seconds": 10.4,
#   "width": 1080, "height": 1920,
#   "face_count_detected": 1,
#   "face_bbox": {"x": ..., "y": ..., "w": ..., "h": ..., "confidence": 0.94},
#   "warnings": []
# }
```

Capture the `path` for use in the next step.

## Smoke test 2 — auto-mode render (English)

```sh
SELFIE_PATH="storage/uploads/demo-tenant-001/avatars/slot1/<uuid>.mp4"   # from previous step

curl -s -X POST http://127.0.0.1:8089/api/v1/videos \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -H "Content-Type: application/json" \
  -d "{
    \"video_subject\": \"Caffeine-free organic energy drink for working parents — 30-day money back\",
    \"video_script\": \"\",
    \"mode\": \"ugc_avatar\",
    \"video_aspect\": \"9:16\",
    \"video_concat_mode\": \"sequential\",
    \"video_transition_mode\": \"FadeIn\",
    \"video_clip_duration\": 5,
    \"video_count\": 6,
    \"voice_name\": \"en-US-AvaMultilingualNeural-Female\",
    \"video_language\": \"\",
    \"paragraph_number\": 1,
    \"script_mode\": \"auto\",
    \"speaker_reference_path\": \"${SELFIE_PATH}\"
  }" | jq

# Expected: {"status":200,"data":{"task_id":"<uuid>"}}
```

Then poll for completion:

```sh
TASK=<task_id>
until [[ "$(curl -s http://127.0.0.1:8089/api/v1/videos/${TASK} | jq -r .status)" == "complete" ]]; do
  sleep 4
  curl -s http://127.0.0.1:8089/api/v1/videos/${TASK} | jq -r '.progress, .stage'
done

ls -la storage/tasks/${TASK}/final-1.mp4
open storage/tasks/${TASK}/final-1.mp4   # macOS — plays in QuickTime
```

**Acceptance**:
- `final-1.mp4` exists and is > 1MB.
- Played in QuickTime: 9:16 portrait, mouth movements match the words.
- Audio is in English (Ava voice).
- Script content is on-topic for "caffeine-free energy drink for working parents".

## Smoke test 3 — Arabic-voice render (multilingual check)

Same selfie as smoke test 2, different voice. Verifies SC-003 (face quality unchanged across languages) and SC-004 (Auto matches voice locale).

```sh
curl -s -X POST http://127.0.0.1:8089/api/v1/videos \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -H "Content-Type: application/json" \
  -d "{
    \"video_subject\": \"Caffeine-free organic energy drink for working parents — 30-day money back\",
    \"video_script\": \"\",
    \"mode\": \"ugc_avatar\",
    \"video_aspect\": \"9:16\",
    \"video_count\": 1,
    \"video_clip_duration\": 30,
    \"voice_name\": \"ar-EG-SalmaNeural-Female\",
    \"video_language\": \"\",
    \"script_mode\": \"auto\",
    \"speaker_reference_path\": \"${SELFIE_PATH}\"
  }" | jq
```

**Acceptance**:
- Same person's face appears in the output as in smoke test 2.
- Audio is now in Egyptian Arabic.
- Subtitles are in Arabic with proper RTL rendering (GeezaPro font auto-swap fired).
- Lip movements match the Arabic phonetics.

## Smoke test 4 — verbatim mode (script control)

```sh
curl -s -X POST http://127.0.0.1:8089/api/v1/videos \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -H "Content-Type: application/json" \
  -d "{
    \"video_subject\": \"Pasta sauce launch\",
    \"video_script\": \"Tired of bland weeknight dinners? Our garden-fresh tomato sauce ships frozen and unfreezes in ninety seconds. Visit pasta.example.com — free shipping this week.\",
    \"mode\": \"ugc_avatar\",
    \"video_aspect\": \"9:16\",
    \"video_count\": 1,
    \"video_clip_duration\": 20,
    \"voice_name\": \"en-US-AvaMultilingualNeural-Female\",
    \"script_mode\": \"verbatim\",
    \"speaker_reference_path\": \"${SELFIE_PATH}\"
  }" | jq
```

**Acceptance**:
- Audio matches the pasted script word-for-word.
- LLM was NOT invoked — verify via L3 logs (no "marketing_script: requesting" line for this task).

## Smoke test 5 — audio overflow → ping-pong loop

Use a SHORT (5-second) selfie + a LONG (e.g. 60-second target) script. The audio will be ~25-30s, exceeding the selfie's 5s duration → triggers FR-015's loop extension.

```sh
SELFIE=/path/to/5second-selfie.mp4
# Upload that selfie first (smoke test 1), then:

curl -s -X POST http://127.0.0.1:8089/api/v1/videos \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -H "Content-Type: application/json" \
  -d "{
    \"video_subject\": \"Detailed product walkthrough — features, pricing, comparison vs competitors, and why we win\",
    \"mode\": \"ugc_avatar\",
    \"video_aspect\": \"9:16\",
    \"video_count\": 1,
    \"video_clip_duration\": 30,
    \"voice_name\": \"en-US-AvaMultilingualNeural-Female\",
    \"script_mode\": \"auto\",
    \"speaker_reference_path\": \"<short-selfie-path>\"
  }" | jq
```

**Acceptance**:
- L3 logs include `lip_sync.extend_reference_to_duration: ref=5.0s target=30.0s loops=6`.
- Final video is ~30s long.
- Watching the output: speaker's body motion reverses smoothly at the 5s, 10s, 15s marks (ping-pong pivot points). No visible jump cuts.

## Smoke test 6 — face validation rejection

```sh
LANDSCAPE=/path/to/landscape-no-face.mp4

curl -s -X POST http://127.0.0.1:8089/api/v1/avatars/upload \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -F "file=@${LANDSCAPE}" | jq

# Expected: 400 with error_code=no_face_detected
```

**Acceptance**: rejection happens BEFORE any expensive processing (no GPU/CPU work charged).

## Wizard smoke (L1)

Open http://localhost:3001/modes/ugc-avatar in a browser:

1. **Step 1 — Selfie**: drag-drop a 10s selfie. Wizard shows the detected face's bounding box overlay + the chosen face thumbnail. If multiple faces detected, the warning banner appears.
2. **Step 2 — Script**: pick `Auto` and enter a product brief.
3. **Step 3 — Voice**: pick `Salma (Egypt, female)`.
4. **Step 4 — Generate**: click the neon CTA. Progress UI advances through stages: Validating → Script → Voice → (Loop) → Lip-sync → Subtitles → Finalizing.
5. **Step 5 — Result**: 9:16 MP4 plays inline, downloadable.

Total wizard wall-clock: ~2-3 minutes for a 30-second output. Long-form (5-min target) ~6-8 minutes.

## Failure-mode coverage

| Scenario | How to test | Expected error |
|---|---|---|
| Selfie has no face | upload a landscape video | `400 no_face_detected` |
| Selfie too short | upload 3s clip | `400 duration_out_of_range` |
| Verbatim with empty script | leave script field empty in Verbatim mode | wizard blocks dispatch with "Verbatim requires a script" |
| Reference file deleted between upload and render | manually `rm` the slot file before clicking Generate | render fails with `speaker_reference_not_found` |
| MuseTalk weights missing | unset `MUSETALK_MODEL_DIR` and restart L3 | `503 lip_sync_engine_unavailable` |
| Mock engine path | set `LIP_SYNC_ENGINE=mock`, run any smoke | output MP4 is the speaker reference unchanged (no lip-sync), useful to test the rest of the pipeline |

## Performance targets

| Target output duration | SC-001 expectation | Hardware assumption |
|---|---|---|
| 30 seconds | < 180s end-to-end | RTX 4090 / A10 in production; ~5 min on M3 Pro / MPS |
| 1 minute | < 300s | scales near-linearly |
| 3 minutes | < 6 min | scales near-linearly |
| 5 minutes | < 8 min | scales near-linearly |
