# Quickstart: Video Duration + Variations + Preview Gate

**Feature**: 002-video-duration-variations

End-to-end localhost run steps to exercise this feature once Step 1 (Next.js frontend) and Step 2 (Layer 2 stub) are available. The quickstart assumes you are validating the feature on a macOS or Linux dev machine with Python 3.11, Node 20, Redis, FFmpeg, and ImageMagick installed.

---

## Prerequisites

1. **This repo** (Layer 3 rendering engine) cloned at `~/code/MoneyPrinterTurbo/`:
   ```sh
   cd ~/code/MoneyPrinterTurbo
   uv sync                                # installs Python deps
   cp config.example.toml config.toml     # edit to set Pexels + LLM keys
   ```

2. **Frontend repo** cloned as a sibling at `~/code/visualai-frontend/`:
   ```sh
   cd ~/code/visualai-frontend
   pnpm install
   cp .env.example .env.local             # set NEXT_PUBLIC_LAYER3_URL=http://localhost:8080
   ```

3. **Redis** running on `localhost:6379` (Docker: `docker run -p 6379:6379 redis:7-alpine`).

4. **Layer 2 stub** (only required to exercise the full preview-gate path in Step 2+). During Step 1 the frontend calls Layer 3 directly and the preview gate is simulated client-side; skip this prerequisite.

---

## Smoke test 1: short-path variations (duration ≤ 30 s)

Validates User Story 1 + User Story 2 together. No preview gate.

1. Start Layer 3:
   ```sh
   cd ~/code/MoneyPrinterTurbo
   python main.py
   # Should log: "Listening on http://0.0.0.0:8080"
   ```

2. Start the frontend:
   ```sh
   cd ~/code/visualai-frontend
   pnpm dev
   # Opens http://localhost:3000
   ```

3. In the browser:
   - Click the **Short Marketing Video** card on the dashboard.
   - Enter or paste a product URL (any product page) in Step 1 of the wizard.
   - In Step 3, drag the duration slider to **22 seconds**.
   - Click the **Variations** stepper to **3**.
   - Click the neon-blue **Create 3 variations** CTA.

4. Observe:
   - The Generation Progress UI shows **3 stacked tracks** labeled Variation 1 / 2 / 3.
   - Each progresses through `script → voice → material → assembly → complete`.
   - All three finish within **≤ 3 minutes** (SC-002 short path).
   - The results screen shows **3 playable thumbnails**, each ~22 s of runtime (± 1 s).

5. Verify duration invariant (SC-001):
   ```sh
   for f in ~/code/MoneyPrinterTurbo/storage/tasks/*/final-*.mp4; do
     ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"
   done
   # Every value MUST be between 21.0 and 23.0 seconds.
   ```

---

## Smoke test 2: long-path preview gate (duration > 30 s)

Validates User Story 3. Requires Layer 2 stub (Step 2+). During Step 1, see the "Step 1 simplification" note in [contracts/layer2-to-layer3.md](contracts/layer2-to-layer3.md).

1. Start Redis, Layer 3, Layer 2 stub (at `http://localhost:9090`), and the frontend (with `NEXT_PUBLIC_LAYER2_URL=http://localhost:9090`).

2. In the browser:
   - Open the Short Marketing Video wizard.
   - Paste the same product URL.
   - Drag the duration slider to **75 seconds**.
   - Set Variations to **3**.
   - Click **Create 3 variations**.

3. Observe the preview phase:
   - The UI shows **3 parallel preview tracks**, each producing a 5-second MP4.
   - All three previews complete within **≤ 45 seconds** (SC-002 preview path).
   - The screen transitions to `PreviewApprovalGrid` — three 5-second videos with **Approve** and **Reject** buttons.
   - A banner reads: `Approving will commit the full 75s render and N credits.`

4. Approve 1, reject 2:
   - Click **Approve** on Variation 1.
   - Click **Reject** on Variations 2 and 3.
   - Observe: credit holds for the rejected variations release within 10 s (FR-021).

5. Observe the full-render phase:
   - Only **one full-render track** appears (for Variation 1).
   - It completes within **≤ 5 minutes** (SC-002 post-approval).
   - The result plays at exactly **75 s ± 1 s**.

6. Verify the preview-to-full equivalence (SC-005):
   ```sh
   # Compare the preview MP4 with the first 5 s of the full MP4
   cd ~/code/MoneyPrinterTurbo/storage/tasks/<task_id>/
   ffmpeg -y -i final-full-0.mp4 -t 5 -c copy first5-of-full.mp4
   ffprobe -show_streams final-preview-0.mp4  first5-of-full.mp4 \
     | diff -u /dev/fd/3 /dev/fd/4 3< <(ffprobe ...) 4< <(ffprobe ...)   # illustrative
   ```
   Or run the regression test:
   ```sh
   cd ~/code/MoneyPrinterTurbo
   pytest test/services/test_preview_equivalence.py -v
   ```

---

## Smoke test 3: credit invariant (SC-007)

Runs against Layer 2 directly; Layer 3 is not involved.

1. Trigger a job with `duration=60, variation_count=3`. Initial hold = `3 × full_cost`.
2. Wait for all three previews to render. Ledger should now show `3 × preview_cost` debited.
3. Approve 1, reject 2.
4. Wait for the full render to complete.
5. Query the credit ledger:
   ```sql
   SELECT amount_reserved, amount_debited, amount_released
   FROM credit_holds
   WHERE job_id = '<job_id>';
   ```
   Expected invariant: `amount_debited + amount_released = amount_reserved`.
   Expected values: `amount_debited = preview_cost × 3 + (full_cost - preview_cost) × 1`, `amount_released = (full_cost - preview_cost) × 2`.

---

## Smoke test 4: timeout path (24 h)

1. Trigger a preview-gated job.
2. Wait for previews to reach `awaiting_approval`.
3. Do NOT click Approve or Reject.
4. Fast-forward Layer 2's expiry worker (set `TEST_EXPIRY_OVERRIDE_MINUTES=1` env var) so the job expires after 1 minute instead of 24 hours.
5. After expiry:
   - `VideoJob.state = expired`.
   - `amount_released = amount_reserved - (preview_cost × N)`.
   - Preview assets remain viewable (no deletion).
   - Layer 3 received no full-render calls (verify in Layer 3 logs).

---

## Failure-path spot checks

| Test | Setup | Expected |
|---|---|---|
| **Pydantic validation** | `curl -X POST http://localhost:8080/api/v1/videos -d '{"total_duration_seconds": 120, ...}'` | HTTP 422, error `total_duration_seconds must be between 5 and 90` |
| **Render mid-failure** | Kill FFmpeg during a render (e.g., `killall ffmpeg`) | Layer 3 emits `mpt:task:{id}:failed`; Layer 2 retries up to 2× free |
| **Collapsed variations** | Use a very generic product URL and seed = 0 | `PreviewApprovalGrid` sets `collapseDetected = true`; `Regenerate with stronger diversity` CTA appears |

---

## Step-1 localhost variant (no Layer 2)

For tonight's MVP:
1. Skip Layer 2 stub entirely.
2. Only duration ≤ 30 s works end-to-end.
3. Long-duration flow shows the approval UI but uses a client-side fake preview (first 5 s trim of a single full render) — this is documented in `STEP1_DEBT.md` as a Step-2 repayment item.

Smoke test 1 is the only one that fully exercises against tonight's stack. Smoke tests 2–4 become available in Step 2.
