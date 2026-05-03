# Quickstart — Mode 3 Long-Form Video Generator

**Audience**: Engineer landing on the branch for the first time, or a reviewer wanting to smoke-test the spec.
**Created**: 2026-05-03

## Prerequisites

- Layer 3 (this repo) running on `:8090` per the existing `python main.py`.
- Layer 2 (`visualai-orchestration`) running on `:8089` (matches spec 015's port — 8088 is squatted by Docker on macOS).
- Layer 1 (`visualai-frontend`) running on `:3001` via `pnpm dev`.
- `.env` files current — Layer 2 needs `LAYER2_DEMO_BEARER`, `OPENAI_API_KEY` (script generation), the existing voice provider keys, and the Pixabay key (or Google Gemini key for the URL-input visuals path).
- Spec 012's URL scraping shipped (`/api/scrape-url`) — required for the URL-input flow only.

## End-to-end flow (US1 — topic prompt)

1. Open `http://localhost:3001/`.
2. Click the "Long-Form Video" card (third card, lucide `monitor-play` icon).
3. **Step 1 — Input**: pick the "Topic prompt" pill. Type "How AI is changing logistics in 2026".
4. **Step 2 — Config**: leave duration at `3 min`, voice at the default `en-US-AvaMultilingualNeural`, music "None".
5. Click **Generate**. Progress bar advances through "Generating script" → "Synthesizing voice" → "Fetching visuals" → "Assembling video".
6. Within ~3–5 minutes (median per SC-001), an inline `<video>` plays the assembled 16:9 MP4.
7. Click **Download**. File saves as `long-form-how-ai-is-changing-logistics-in-2026-2026MMDD-HHMMSS.mp4`.
8. Navigate to **My Assets**. The new video card sits at the top of the grid, 16:9 thumbnail.

### Acceptance evidence to capture

- Video duration is 2:45 ≤ x ≤ 3:15 (FR-017, SC-002 — ±15s on 3-minute target).
- Subtitles render between 75% and 90% of frame height (FR-006, SC-003).
- File is approximately 1920×1080 (verify via `ffprobe` if reviewing rigorously).
- Cost log line on Layer 2 reports ≤ $0.50 (SC-005).

## End-to-end flow (US2 — URL source)

1. Step 1: pick "Source URL" pill. Paste a public product page URL.
2. Steps 2–8 same as above.
3. Verify the script references facts from the scraped page (review the Layer 2 log line `script_text` excerpt — the script should mention the product name).
4. If the URL is unreachable, the wizard surfaces a clear error and offers to convert the URL to a topic prompt (FR-016).

## End-to-end flow (US4 — pre-written script)

1. Step 1: pick "Pre-written script" pill. Paste a 400-word script (≈ 3 min at 150 wpm).
2. Step 2: select duration `3 min` (matches script length).
3. Steps 3–8 same.
4. Verify narration matches the pasted script verbatim (script-gen is skipped for this source type per data-model.md).

## Backend smoke (no UI)

```sh
# Layer 2 — POST a topic
curl -X POST http://127.0.0.1:8089/api/v1/long-form-videos \
  -H "Authorization: Bearer demo-bearer-replace-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "topic",
    "source_text": "How AI is changing logistics in 2026",
    "target_duration_seconds": 180,
    "voice_id": "en-US-AvaMultilingualNeural",
    "music_id": null
  }'
# Expect: 200 OK after ~3-5 min with status="complete" and a pre-signed output_video_url

# Layer 2 — list all
curl -H "Authorization: Bearer demo-bearer-replace-in-production" \
  http://127.0.0.1:8089/api/v1/long-form-videos | jq '.[] | {id, status, target_duration_seconds, actual_duration_seconds}'
```

## Test commands (per repo)

```sh
# Layer 3 — mode registry contract test
pytest test/services/modes/test_long_form.py -v

# Layer 2 — route + store tests
cd ../visualai-orchestration && .venv/bin/pytest tests/routes/test_long_form_videos.py -v

# Layer 1 — wizard render test (Vitest if present, otherwise component smoke)
cd ../visualai-frontend && pnpm test -- src/app/modes/long-form
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Layer 2 returns `404 not_found` for `/api/v1/long-form-videos` | Route module not registered in `app/main.py` | Add `app.include_router(long_form_videos.router)` |
| 504 `provider_timeout` after ~10 minutes | Layer 3 hung mid-render OR voice synthesis loop | Inspect Layer 3 logs for `tenant_id=demo-tenant-001` lines; restart Layer 3 |
| Video plays but is 9:16, not 16:9 | `params.video_aspect` not set to `"16:9"` in Layer 2's `VideoParams` payload | Inspect Layer 2 log line for the outbound payload; fix in `app/routes/long_form_videos.py` |
| My Assets shows a card with no thumbnail / black preview | `final-1.mp4` is below 100KB (failed render) | Layer 2's list endpoint should already filter — if not, check the size threshold in `long_form_store.py` |
| Subtitles appear in the center (not lower-third) | Mode 3's registry not consulted; default `subtitle_position="center"` leaked through | Check `app/services/modes/long_form.py` is imported by Layer 3's mode dispatcher |
| Script text reads as one paragraph instead of hook/body/summary | LLM ignored the structured prompt | Inspect `generate_long_form_script` prompt; consider adding a JSON schema enforced by the model |

## Verification of constitution gates

After running through US1 once:

- ✅ Principle II — `git diff main..016-long-form-video` in this repo touches only `app/services/modes/long_form.py`, `app/services/llm.py`, `app/models/schema.py`.
- ✅ Principle IV — Layer 3 logs show no outbound HTTP to OpenAI/Gemini/Pixabay/etc. — those calls are upstream of Layer 3, in Layer 2 / Layer 2.5.
- ✅ Principle V — `app/services/modes/long_form.py` is the single source of truth for Mode 3's aspect/duration/subtitle config.
- 🟡 Principle III — demo-tenant in payloads (acknowledged debt; spec 014 closes).
