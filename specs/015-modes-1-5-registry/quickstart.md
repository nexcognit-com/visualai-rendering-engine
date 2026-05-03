# Quickstart: Step 3 — Modes 1 + 5 + Mode Registry End-to-End

**Date**: 2026-05-03
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This walks through a full manual smoke test after Step 3 lands. Three modes should be live:
- Mode 1 — Product Shoot Generator (sync, ~30s, 6 images)
- Mode 2 — Short Marketing Video (existing, regression check)
- Mode 5 — Faceless Channel Automation (new, ~60-90s, 1 video)

If any of these fail, the corresponding PR isn't ready to merge.

---

## Prerequisites

- All three repos cloned at sibling paths under `NexCognit-Content-generator/`:
  - `MoneyPrinterTurbo/` (Layer 3)
  - `visualai-orchestration/` (Layer 2)
  - `visualai-frontend/` (Layer 1)
- `.env` files populated:
  - Layer 3 — Pexels + Pixabay keys (existing)
  - Layer 2 — `LAYER2_JWT_SIGNING_KEY`, `LAYER2_SIGNING_KEY` (NEW), `LAYER25_NANOBANANA_API_KEY` (NEW), `LAYER25_IMAGE_PROVIDER=nanobanana`
  - Layer 1 — `LAYER2_BASE_URL=http://localhost:8088`, `LAYER2_DEMO_BEARER_TOKEN=<minted JWT>`
- A test product image at hand: a clean photo of any single object (water bottle, mug, watch, sneakers).

---

## Step A — Boot all three services

**Terminal 1 — Layer 3 (Rendering Engine)**
```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo
python main.py
# Expect: "Listening on http://0.0.0.0:8090" + JWT middleware loaded
```

**Terminal 2 — Layer 2 (Orchestration)**
```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-orchestration
python main.py
# Expect: "Listening on http://0.0.0.0:8088" + Layer 2.5 router registered + signing keys validated
```

**Terminal 3 — Layer 1 (Frontend)**
```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/visualai-frontend
pnpm dev
# Expect: "Local: http://localhost:3001"
```

**Health check**:
```sh
curl -s http://localhost:8090/health  # Layer 3
curl -s http://localhost:8088/health  # Layer 2
open http://localhost:3001            # Layer 1
```

All three should respond. If Layer 2 fails to start with a missing-env error, the production-safety check is doing its job — populate `.env` and retry.

---

## Step B — Dashboard activation check

1. Open `http://localhost:3001` in a browser.
2. Verify 5 mode cards render with NexCognit branding (dark navy background, neon-yellow accents).
3. Click states:
   - **Mode 1 (Product Shoot Generator)** — clickable; cursor pointer; navigates to `/modes/product-shoot`
   - **Mode 2 (Short Marketing Video)** — clickable; navigates to `/modes/short-video` (unchanged)
   - **Mode 3 (Long-Form 16:9)** — non-clickable; "Coming in Step 4" badge visible
   - **Mode 4 (UGC Avatar)** — non-clickable; "Coming in Step 4" badge
   - **Mode 5 (Faceless Channel)** — clickable; navigates to `/modes/faceless-channel`

**FAIL CRITERIA**: any clickable card that should be locked, or any locked card that should be live.

---

## Step C — Mode 5 end-to-end

1. From dashboard, click "Faceless Channel Automation".
2. Wizard step 1: type topic = `"5 surprising Mediterranean diet facts"` OR click the preset chip.
3. Wizard step 2: pick voice = `"en-US-AriaNeural"` (default), pick music = first preset.
4. Click neon-yellow "Generate Video" CTA.
5. Wizard step 3: progress UI animates through stages: `generating script → fetching B-roll → synthesizing voice → assembling video`.
6. Within ~90s, MP4 plays inline. Vertical 9:16 aspect, ~30-45s duration, generic stock footage relevant to Mediterranean food.

**Backend trace** (in another terminal):
```sh
tail -f visualai-orchestration/logs/layer2.log | grep faceless
# Should see: Layer 2 forwards to Layer 3 with mode=faceless; visuals.json sidecar has pre_signed_clip_urls=null

tail -f MoneyPrinterTurbo/logs/layer3.log | grep mode=faceless
# Should see: modes.pick("faceless") → faceless module dispatches generate_script + generate_terms;
# material.download_videos hits Pexels direct (Mode 5 carve-out)
```

**FAIL CRITERIA**:
- Video doesn't render (any stage stuck > 2 minutes)
- B-roll is unrelated to Mediterranean diet (means term generation broke)
- `visuals.json` shows `pre_signed_clip_urls` non-null (Mode 5 should fall back to Pexels direct)
- Layer 3 logs show `material.no_visuals_source` error
- Output aspect ratio isn't 9:16

---

## Step D — Mode 1 end-to-end

1. Return to dashboard. Click "Product Shoot Generator".
2. Wizard step 1: drag-and-drop a product image (or click to browse). Optionally type description = `"matte black water bottle on wooden surface"`.
3. Click neon-yellow "Generate Photoshoot" CTA.
4. Wizard step 2: spinner with "Generating studio photos..." (~30s).
5. Within ~30s, 6 thumbnails render in a grid. Each is a different studio-quality shot of the same product.
6. Click any thumbnail — opens lightbox preview.

**Backend trace**:
```sh
tail -f visualai-orchestration/logs/layer2.log | grep product_shoot
# Should see:
#   POST /api/v1/uploads (source image)
#   POST /api/v1/product-shoots
#   layer25.image_router.generate_studio_photos called
#   nanobanana provider.generate → status 200
#   Either "6 individual images" OR "contact sheet detected, slicing"
#   6 files written to storage/tasks/ps_<id>/
#   product_shoot.complete latency_ms=~32000 cost_usd=0.24
```

**Layer 3 should be untouched**: `tail -f MoneyPrinterTurbo/logs/layer3.log` shows nothing during this test. Mode 1 never reaches Layer 3.

**FAIL CRITERIA**:
- Generation takes > 90s (timeout)
- < 6 images returned (Layer 2.5 normalisation broke)
- Output images are unrelated to the source image (provider not honoring image input)
- Output URLs return 403/410 when clicked (signing or expiry broken)
- Layer 3 logs show ANY activity (architectural violation)

---

## Step E — Mode 2 zero-regression check

This is the existence proof for FR-026 (Step 3 must not break Mode 2).

1. Return to dashboard. Click "Short Marketing Video".
2. Run the same flow that worked at end-of-Step-1 / Step-2:
   - Paste any product URL (e.g. an Amazon product page)
   - Pick voice + music
   - Click Generate
3. Within ~90s, a 9:16 MP4 should render — same shape as before Step 3.

**Backend trace**:
```sh
tail -f MoneyPrinterTurbo/logs/layer3.log | grep mode=short
# Should see: modes.pick("short") → short module dispatches generate_script + generate_terms
# (formerly inline branches in llm.py; now registry-dispatched)
# material.download_videos: pre_signed_clip_urls present (NEW — was Pexels-direct pre-Step-3)
# OR for visuals_mode=hybrid: hybrid path retains direct Pexels (residual debt #3)
```

**FAIL CRITERIA**:
- Render time > 110s (>5% regression vs Step-2 baseline of ~90s)
- Output MP4 differs visibly from Step-2 baseline given same input
- `visuals.json` for `visuals_mode="auto"` is missing `pre_signed_clip_urls`
- Any test in `test/services/modes/test_short.py` snapshot fails

---

## Step F — Registry extensibility self-test

Per FR-021, adding a new mode should be a one-module change. Verify:

```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo
python -c "from app.services import modes; print(modes.supported())"
# Expect: ['short', 'faceless']

python -c "from app.services import modes; m = modes.pick('faceless'); print(m.name, m.default_aspect_ratio)"
# Expect: faceless VideoAspect.portrait

python -c "from app.services import modes; modes.pick('product_shoot')"
# Expect: KeyError: "unsupported_mode: 'product_shoot'..."

python -c "from app.services import modes; modes.pick('long')"
# Expect: KeyError (Mode 3 not registered yet)
```

**FAIL CRITERIA**: any of the above behaves differently. The registry shape IS the contract for Step 4's mode additions.

---

## Step G — Pre-signed URL handshake check

Validates the Layer 2 → Layer 3 boundary works as designed.

```sh
# 1. Mint a fresh JWT (use the demo bearer)
JWT=$(cat .env | grep LAYER2_DEMO_BEARER_TOKEN | cut -d'=' -f2)

# 2. Trigger Mode 2 with visuals_mode=auto
curl -X POST http://localhost:8088/api/v1/videos \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"mode":"short","video_subject":"matcha","visuals_mode":"auto","script_mode":"auto","voice_name":"en-US-AriaNeural"}' \
  | jq '.'

# 3. Read the sidecar Layer 2 wrote:
TASK_ID=<from response>
cat /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo/storage/tasks/$TASK_ID/visuals.json | jq '.pre_signed_clip_urls'

# Expect: array of HTTP URLs starting with http://localhost:8088/_signed/...
# Each URL has format: /_signed/<32-hex-sig>/<tenant_id>/<filename>?expires=<unix>

# 4. Curl one of those URLs WITHOUT a JWT (HMAC is the auth):
curl -I "<one of the URLs>"
# Expect: 200 OK (file exists)

# 5. Tamper the signature → 403:
curl -I "<URL with one char of sig changed>"
# Expect: 403 url_invalid_signature

# 6. Tamper the expiry to a past unix timestamp → 410:
curl -I "<URL with expires=1>"
# Expect: 410 url_expired
```

**FAIL CRITERIA**: any of the verification rules above don't hold. The pre-signed URL pattern IS the constitutional bridge between Layers 2 and 3.

---

## Step H — Constitution amendment landed

```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo
grep -n "Version: 1.1.0" .specify/memory/constitution.md
# Expect: at least one match in the Sync Impact Report header

grep -n "app/services/modes/" .specify/memory/constitution.md
# Expect: in the fork-surface enumeration of Principle II

grep -A2 "Mode 1" .specify/memory/constitution.md
# Expect: documented as actively implemented (not "reserved")
grep -A2 "Mode 5" .specify/memory/constitution.md
# Expect: documented as actively implemented
```

**FAIL CRITERIA**: any constitution claim above missing. PR-A doesn't merge without the amendment.

---

## Step I — STEP1_DEBT.md updated

```sh
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/MoneyPrinterTurbo
cat STEP1_DEBT.md
```

After Step 3, the file should show:

| Row | Status |
|---|---|
| #1 (Layer 3 scope — direct frontend→Layer 3) | already struck (Step 2) |
| #2 (Multi-tenant context) | already struck (Step 2) |
| #3 (External Asset Acceptance) | **partially struck** — note "Mode 2 Auto path repaid in <commit>; hybrid path remaining" |
| #4 (Mode-Aware Rendering) | **struck through** — note "repaid in <commit>" |
| #5 (Surgical Fork — task.py) | **struck through** — note "repaid in <commit>" |
| #6 (Layer-3 upload carve-out) | unchanged (Step 4) |
| #7 (Moderation deferred) | unchanged (Step 5+) |

---

## Pass criteria for Step 3 acceptance

All of the following MUST be true before the spec is considered shipped:

- [ ] Step A — all three services boot cleanly
- [ ] Step B — dashboard shows 3 active + 2 locked cards
- [ ] Step C — Mode 5 end-to-end works
- [ ] Step D — Mode 1 end-to-end works (sync, ~30s, 6 images)
- [ ] Step E — Mode 2 still works (regression baseline)
- [ ] Step F — registry extensibility self-test passes
- [ ] Step G — pre-signed URL handshake validates correctly (200 / 403 / 410)
- [ ] Step H — constitution v1.1.0 amendment landed
- [ ] Step I — STEP1_DEBT.md updated with strikes for #3 (partial), #4, #5
- [ ] All tests in `test/services/modes/`, `test/services/test_material_pre_signed_urls.py`, `tests/router/test_image.py`, `tests/routes/test_product_shoots.py`, `tests/routes/test_pre_signed.py`, `tests/product-shoot.test.ts` pass
- [ ] No code lives in unrelated fork-surface files; touched files match the plan's project structure exactly
