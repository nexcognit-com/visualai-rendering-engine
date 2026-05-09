# Quickstart: Mode 3 long-form 10-minute cap + URL-expiry resilience + WebM selfie uploads

**Feature**: `019-longform-10min-fix` | **Date**: 2026-05-09

Three smoke-test journeys an operator or QA can run against a local dev stack to verify each spec story end-to-end. Each journey is independently testable.

## Prerequisites — local stack up

```
L1 (Next.js wizard)         http://localhost:3000      cd /root/dev/visualai/visualai-frontend && pnpm dev
L2 (orchestration)          http://localhost:8089      cd /root/dev/visualai/visualai-orchestration && ./.venv/bin/python main.py
L3 (rendering — this repo)  http://localhost:8090      cd /root/dev/visualai/MoneyPrinterTurbo && ./.venv/bin/python main.py
```

Confirm all three are listening (`ss -tln | grep -E ':(3000|8089|8090) '`) before each journey.

## Journey A — User Story 1: pick a 10-minute Mode 3 target

**Goal**: confirm the cap raise flows end-to-end through L1 → L2 → L3.

1. Open `http://localhost:3000` and pick **Mode 3 — Long-Form Video** from the mode picker.
2. In the duration choice, verify **8 min** and **10 min** options exist alongside 2/3/4/5 min.
3. Select **10 min**, write any non-empty subject (e.g. "the migration patterns of monarch butterflies"), pick a voice, click Generate.
4. Observe the wizard's progress; do not close the tab.
5. Verify the wizard does not surface a "render timed out" before the render finishes (the L1 poll timeout is 75 min — the render takes ~50–70 min on M-series).
6. When the wizard reports completion, open the resulting MP4 in a browser player.

**Pass criteria** (mirrors spec.md SC-001, SC-002):
- Output MP4 plays end-to-end at 600 ± 5 seconds.
- Subtitle track plays in alignment with audio across the full duration.
- Counting visual cuts manually (or via `ffprobe -show_frames`), segment count is between 30 and 40.

## Journey B — User Story 2: render survives expired pre-signed URLs

**Goal**: confirm the placeholder fallback rescues a render whose fetch step encounters dead URLs.

This journey requires a fixture that forces 403 responses on at least one pre-signed URL. Two ways to inject:

**Option B.1 — manual L2-side TTL trick**:
1. Set `LAYER2_PRESIGN_TTL_SECONDS=2` in `visualai-orchestration/.env` (revert after).
2. Restart L2.
3. Dispatch a Mode 3 render at the 5-minute target (so wall-clock is short enough to exercise quickly).
4. The visual_relevance step mints URLs that expire ~2 seconds later, well before L3 fetches them.

**Option B.2 — code-level fixture**:
1. In a Python REPL, hand-craft a `urls` list where one URL points to a known-expired S3 pre-signed URL (or a local stub returning 403).
2. Call `app.services.material._download_from_pre_signed_urls("test-task", urls)` directly.
3. Inspect the resulting clips dir.

**Pass criteria** (mirrors spec.md SC-003, SC-004, FR-004, FR-005, FR-007):
- The render does not raise `RuntimeError("material.fetch_failed")` on the dead URL(s).
- The L3 log contains a `WARNING` line per dead URL: `material.fetch_failed url='...': url_expired_or_forbidden status=403; writing black-frame placeholder for clip-N`.
- The final MP4 plays at the correct total duration ± 0.2s.
- Subtitle alignment is intact across the full duration.
- The black-frame segments appear at exactly the time slots the dead URLs would have occupied.

## Journey C — User Story 3: browser-recorded WebM selfie upload

**Goal**: confirm a Chromium-recorded WebM selfie uploads on first attempt.

1. Open `http://localhost:3000` in Chrome or any Chromium-based browser. Pick **Mode 4 — UGC Avatar**.
2. In the **Speaker reference** section, click **Record selfie**.
3. Allow camera permission. Record 6–10 seconds of yourself talking to camera.
4. Click upload.

**Pass criteria** (mirrors spec.md SC-005, FR-008, FR-009):
- The upload returns 200 (not the previous 400 `Unsupported MIME: video/webm;codecs=vp8`).
- The "recent selfies" picker shows the new upload immediately after.
- On L3, the persisted file at `storage/uploads/<tenant>/<slot>.mp4` is a valid MP4 — confirm with `ffprobe`:
  - `codec_name = h264`
  - `pix_fmt = yuv420p`
  - no audio stream
- The picker thumbnail loads (i.e. the file is genuinely playable, not just present).

**Negative case** (mirrors FR-010, SC-006):
1. Use `curl -F file=@some.png -F 'Content-Type=image/png' http://localhost:8090/api/v1/uploads/selfie` (with appropriate auth).
2. Verify response: `400` with `{ "detail": { "error_code": "format_unsupported", "message": "Unsupported MIME: image/png" } }`.
3. Repeat with `Content-Type: video/x-flv;codecs=h263+` — verify the message echoes the **full original string**, not just `video/x-flv`.

## Reset between journeys

Each journey is idempotent — no state needs resetting between runs. Failed renders are visible in the wizard's history but do not block subsequent runs.

## Out of scope for quickstart

- Load testing the 10-min cap (SC-001 percentile guarantees) — that's a separate ops/perf-test pass, not a smoke test.
- Twelve Labs spend verification (SC implicit) — observable via the L2 cost dashboard, not L3.
- MediaPipe face-detect failure paths — covered by the existing spec 018 quickstart, not duplicated here.
