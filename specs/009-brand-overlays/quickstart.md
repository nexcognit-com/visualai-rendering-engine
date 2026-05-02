# Quickstart: Brand Overlays

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Audience**: developers verifying or extending the overlay feature; operators reproducing SC-001..SC-006 metrics.

---

## Part 1 — Verify the empty-overlay path (SC-002, zero regression)

Run a baseline render and confirm it's identical to the no-feature behavior. This is the most important verification: existing users MUST see no change.

```sh
# Terminal 1 — MPT backend on :8090 (or whichever port your config.toml has set)
cd MoneyPrinterTurbo && python main.py

# Terminal 2 — visualai-frontend on :3001 (or whatever Next picks)
cd visualai-frontend && pnpm dev
```

In your browser:

1. Open `http://localhost:3001`.
2. Click "Short Marketing Video".
3. Fill the wizard (subject, voice, music) — **leave the Overlays panel collapsed/empty**.
4. Submit. Wait for render.
5. Inspect the resulting MP4 in My Assets.

**Pass criterion (SC-002)**: the render time and the visual output are within 5% of a render performed before this feature shipped. The compositor MUST short-circuit on empty overlays — confirm in the MPT logs:

```
INFO apply_overlays start input=.../final-1.mp4 overlays_count=0
INFO apply_overlays done output=.../final-1.mp4 elapsed_ms=<<5
```

If `elapsed_ms` exceeds ~10 ms with `overlays_count=0`, the fast path is broken — file as a regression.

---

## Part 2 — Verify a single logo overlay (SC-001 P1 acceptance)

```sh
# Pre-stage a test logo (200x200 transparent PNG)
mkdir -p /tmp/visualai-smoke && cd /tmp/visualai-smoke
python3 -c "from PIL import Image, ImageDraw; im = Image.new('RGBA', (200, 200), (0, 0, 0, 0)); d = ImageDraw.Draw(im); d.ellipse([10, 10, 190, 190], fill=(255, 248, 107, 255)); d.text((70, 90), 'NX', fill=(0, 0, 0, 255)); im.save('test-logo.png')"
ls -la test-logo.png   # should show ~3-5 KB
```

In the wizard:

1. Open Step 3, expand the **Overlays** panel.
2. Click "Add overlay" → "Logo".
3. Upload `/tmp/visualai-smoke/test-logo.png`.
4. Pick `bottom-right` corner.
5. Leave size at default (15%) and opacity at default (100%).
6. Submit and wait for render.

**Pass criteria**:

- The wizard shows an inline preview after upload (the picked corner is highlighted).
- The render completes successfully (visible in My Assets with `state: complete`).
- The final MP4 has the yellow circle logo crisply composited in the bottom-right of every frame, sized at ~15% of the video's 1080 px width (so ~162 px wide on a 1080×1920 9:16 render).
- The logo's transparency is preserved (the corner circle is round, not surrounded by a square frame).

If you scrub the timeline and the logo is anywhere except bottom-right, or it's blurry / pixelated, file as a regression against R2 (positioning) or R1 (compositor pattern) of [research.md](./research.md).

---

## Part 3 — Verify a rectangle overlay (P2 acceptance)

In the wizard:

1. Step 3 → Overlays → "Add overlay" → "Rectangle".
2. Pick `top-left` corner.
3. Set size preset to `medium`.
4. Pick color `#3B82F6` (the brand-accent hex from spec 001).
5. Set opacity to 60%.
6. Submit.

**Pass criteria**:

- The final MP4 has a semi-transparent blue rectangle in the top-left of every frame.
- Roughly 30% of the video width wide (the `medium` preset).
- 24 px margin from both top and left edges (default).

---

## Part 4 — Verify the multi-overlay z-order (P3 acceptance)

In the wizard:

1. Step 3 → Overlays → "Add overlay" → "Rectangle". Same config as Part 3 (top-left, medium, blue, 60%).
2. Click "Add overlay" again → "Logo". Upload the same `test-logo.png` from Part 2. Pick `top-left`. Set width to 8% (so it nests inside the rectangle).
3. Submit.

**Pass criterion**: in the final MP4, the rectangle is in the top-left, and the logo sits ON TOP of the rectangle (because logo is later in the list, higher z-order).

If the logo is BEHIND the rectangle, the z-ordering in `apply_overlays` is broken — file against contract C-4 in [compositor-contract.md](./contracts/compositor-contract.md).

---

## Part 5 — Verify error surfacing (SC-004, FR-013)

This part exercises the loud-fail contract. Every overlay-step failure MUST surface to the user; nothing silent.

### 5a — Missing logo file

Edit `script.json` for a test task (or simulate via an API call) to set `overlays[0].source_path = "/nope.png"` and re-trigger the render. Expected:

- The task moves to `state: failed`.
- MPT logs an ERROR line: `apply_overlays failed code=logo_not_found context={'path': '/nope.png'}`.
- The wizard surfaces the failure with a clear message ("logo file is missing — please re-upload").

### 5b — Corrupt PNG upload

```sh
echo "not a real image" > /tmp/visualai-smoke/broken.png
```

Try to upload `broken.png` via the wizard. Expected:

- The frontend rejects the upload before submission with HTTP 415 from the upload endpoint and `error_code: invalid_image`.
- The wizard shows the error inline; render does NOT start.

### 5c — Oversize upload

Use any > 5 MB image. Expected: HTTP 413 with `error_code: file_too_large`. Wizard shows "Logo must be under 5 MB."

If any of these silently succeed (or worse, succeed with overlay-less output), FR-013 is violated.

---

## Part 6 — Run the smoke tests

```sh
cd MoneyPrinterTurbo
pytest test/services/test_overlays.py -v
```

Expected: 4 passing tests covering C-1 through C-7 of [compositor-contract.md](./contracts/compositor-contract.md). Total wall clock < 30 seconds (the synthetic ColorClip stub keeps tests fast).

If a test fails, the contract section it implements is violated — fix the offending code, not the test.

---

## Part 7 — Verify the schema forward-compatibility (SC-006)

```sh
cd MoneyPrinterTurbo
python3 -c "
from app.models.schema import Overlay
o = Overlay(
    kind='logo',
    position='bottom-right',
    source_path='brand-library/tenant_abc/logo_v2.png',  # future Brand Library path
    width_pct=0.15,
    opacity=1.0,
)
print('OK:', o)
"
```

Expected: the model validates cleanly, prints the `Overlay` repr. Confirms that a future Brand Library path string will pass through the v1 Pydantic model without schema change (FR-012).

---

## Operator runbook — adding a new overlay kind in v2

When animation/text overlays land in v2, the recipe is:

1. Add a new value to the `OverlayKind` literal in `schema.py` (e.g., `"text"`).
2. Add the new kind's required fields to the `Overlay` model.
3. Extend the `model_validator` to enforce the new kind's required-field rules.
4. Add a new branch in `apply_overlays()` that builds the right MoviePy clip from the new fields.
5. Update the wizard's overlay panel to expose the new kind.
6. Add new test cases to `test/services/test_overlays.py`.
7. Update [overlay-schema.md](./contracts/overlay-schema.md) with the new shape.

Existing v1 overlays continue to validate unchanged because the new kind is optional and additive.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Logo appears in wrong corner | Position math regression in `apply_overlays` | Re-run the test C-2 / C-3; check `(x, y)` formulas against [research.md R2](./research.md) |
| Logo composited but transparency missing (square frame visible) | `ImageClip` not preserving alpha | MoviePy needs the source PNG to be `RGBA`; verify `Image.open(path).mode == "RGBA"` |
| Rectangle clipped at video edge | Computed `(x+w, y+h)` exceeds video bounds; clamping is on | This is expected per R5 of research.md; reduce `size_preset` or pick a different corner |
| Render time doubled with one overlay | Encoder preset got changed | Confirm `preset="medium"` in `apply_overlays`'s `write_videofile` call |
| `apply_overlays` is called even when `overlays=[]` | Fast path missing | The function MUST short-circuit on empty list before opening the MP4 |
| Upload returns 201 but logo file isn't readable later | Permission bits / disk perms | Confirm files saved with `0o644`; check `storage/uploads/` directory perms |

---

## Related contracts

- [contracts/overlay-schema.md](./contracts/overlay-schema.md) — Overlay JSON shape
- [contracts/upload-endpoint.md](./contracts/upload-endpoint.md) — `POST /api/v1/uploads/logo`
- [contracts/compositor-contract.md](./contracts/compositor-contract.md) — `apply_overlays()` semantics
