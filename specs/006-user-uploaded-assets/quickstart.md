# Quickstart: User-Uploaded Model & Product Assets

**Feature**: 006-user-uploaded-assets
**Goal**: Manually verify the end-to-end flow before declaring spec 006 implemented.

## Prerequisites

1. MPT backend running: `python main.py` from repo root → expect `Listening on http://0.0.0.0:8080`.
2. Frontend running: `pnpm dev` from `../visualai-frontend/` → expect `http://localhost:3000`.
3. Three sample product photos in JPEG/PNG/WebP at 1080×1920 or larger. (Cortex41 example: a dashboard screenshot, a defect-detection clip frame, a manufacturing-line photo.)
4. Optional: one model image (founder portrait or styled shot).

## Part 1 — Pristine state preservation (zero regression)

1. Open `http://localhost:3000/modes/short-video`.
2. Without touching the new Visuals selector, paste a product URL (or write a script), pick a voice, click Generate.
3. **Expected**: render produces Pexels stock B-roll exactly as it did before spec 006 (byte-identical to a pre-006 render with the same inputs).
4. **Verify**: `cat storage/tasks/<task_id>/script.json | jq '.asset_audit'` returns `{ "visuals_mode": "auto", "auto_pexels_used": true, "pexels_clip_count": <n> }`.

## Part 2 — Single product image (US1 minimum)

1. In the wizard, scroll to the Script & Voice step.
2. Click the **Use my own assets** pill in the Visuals row.
3. **Expected**: an upload area appears below the pill with one Model slot (optional) and three Product slots (1 required).
4. Drag a single product photo into Product slot 1.
5. **Expected**: progress bar fills, thumbnail appears with green check + filename within ~3 seconds.
6. Type or accept a script. Click Generate.
7. **Expected**: render completes within ~90 seconds. Resulting MP4 plays inline.
8. **Verify visually**: every frame of the video is the user's product photo with subtle zoom/pan motion. ZERO Pexels frames.
9. **Verify programmatically**:
   ```sh
   cat storage/tasks/<task_id>/script.json | jq '.asset_audit'
   ```
   Expected output:
   ```json
   {
     "visuals_mode": "user_uploaded",
     "auto_pexels_used": false,
     "pexels_clip_count": 0,
     "model_asset": null,
     "product_assets": [
       { "uuid": "...", "filename": "your-photo.jpg",
         "content_hash": "sha256:...",
         "kenburns_clip_path": "storage/tasks/.../uploaded-1.mp4",
         "screen_time_seconds": ... }
     ]
   }
   ```

## Part 3 — Three products + model bookend (US2 happy path)

1. Open a fresh wizard session.
2. Click **Use my own assets**.
3. Upload one image to the Model slot, three images to the Product slots in order.
4. Generate.
5. **Expected**: video opens with model image (zoom-in over 3–5s), transitions through three product images in upload order (each ~2–4s with zoom + light pan), closes with model image (2–4s).
6. **Verify**: `script.json#asset_audit.model_asset.placement === "opening+closing"`, `product_assets[i].placement === "middle-i+1"`.
7. **Verify SC-007**: `jq '.asset_audit.product_assets[].screen_time_seconds, .asset_audit.model_asset.screen_time_seconds' < script.json` — every value ≥ 2.0.

## Part 4 — Mode switching mid-session (US3)

1. After Part 3 completes, click "Make another."
2. Wizard re-opens. Script + voice retained from prior render.
3. Toggle Visuals selector back to **Auto (stock)**.
4. **Expected**: upload thumbnails remain visible (so a re-toggle restores them) but greyed out / labeled "not used in Auto mode."
5. Generate.
6. **Expected**: render uses Pexels stock — ZERO of the previously uploaded images appear.
7. **Verify**: `script.json#asset_audit` for this new task has `visuals_mode: "auto"`, `auto_pexels_used: true`.

## Part 5 — Validation errors

1. New wizard session. Toggle to **Use my own assets**.
2. Try to click Generate with zero product images uploaded.
3. **Expected**: Generate button is disabled with tooltip "Upload at least one product image to continue."
4. Drag a `.tiff` file into a product slot.
5. **Expected**: client-side rejection (or server 400) with message "JPEG, PNG, or WebP only."
6. Drag an 11 MB file.
7. **Expected**: 413 from server with `error_code: "file_too_large"` rendered as user-facing "Max 10 MB per image."
8. Drag a 600×400 image.
9. **Expected**: 200 OK + soft warning toast "This will look soft; prefer images ≥ 1080 px." Slot still fills successfully.

## Part 6 — Backward compatibility (non-VisualAI client)

Simulate a legacy upstream MPT WebUI request (no `visuals_mode` field):

```sh
curl -s -X POST http://localhost:8080/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{
    "video_subject": "morning routine",
    "video_script": "",
    "video_aspect": "9:16",
    "voice_name": "en-US-JennyNeural-Female",
    "video_count": 1,
    "paragraph_number": 1
  }'
```

**Expected**: 200 with `task_id`, render proceeds via existing Pexels code path. No 4xx Pydantic errors. `script.json#asset_audit.visuals_mode === "auto"` (default applied silently).

## Part 7 — SC-001 invariant audit (production-like check)

After all parts above:

```sh
for taskdir in storage/tasks/*/; do
  audit=$(jq '.asset_audit' "$taskdir/script.json" 2>/dev/null)
  mode=$(echo "$audit" | jq -r '.visuals_mode')
  pexels_used=$(echo "$audit" | jq -r '.auto_pexels_used')
  if [ "$mode" = "user_uploaded" ] && [ "$pexels_used" = "true" ]; then
    echo "FAIL: $taskdir — user_uploaded render contains Pexels frames"
  fi
done
```

**Expected**: zero "FAIL" lines. This is the SC-001 invariant.

## Part 8 — Test suite

```sh
# Backend
.venv/bin/pytest test/services/test_uploaded_visuals.py test/controllers/test_image_upload.py -v
# Expected: all 30+ tests pass (10 IU + 10 VW + 10 MD + others)

# Frontend
cd ../visualai-frontend && pnpm test visuals-mode
# Expected: all 10 WV tests pass
```

## Sign-off

Spec 006 is implementation-complete when:

- [ ] Parts 1–7 manual checks pass.
- [ ] Part 8 test suites green.
- [ ] `STEP1_DEBT.md` cross-references row(s) for the Layer-3 carve-out and `MODERATION_REQUIRED=False`.
- [ ] Constitution check re-confirmed in the PR description: only `schema.py` + `material.py` + `uploads.py` touched in this repo (zero `task.py` / `video.py` / `voice.py` edits).
- [ ] PR opened with the standard spec-006 template body and referenced against the Jira Epic.
