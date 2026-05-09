# Quickstart: Brand Library

**Feature**: `020-brand-library` | **Date**: 2026-05-10

Three smoke-test journeys mapping to the three user stories in spec.md. Each is independently runnable against a local stack.

## Prerequisites — local stack up

```
L1 (Next.js wizard)         http://localhost:3000      cd /root/dev/visualai/visualai-frontend && pnpm dev
L2 (orchestration)          http://localhost:8089      cd /root/dev/visualai/visualai-orchestration && ./.venv/bin/python main.py
L3 (rendering — this repo)  http://localhost:8090      cd /root/dev/visualai/MoneyPrinterTurbo && ./.venv/bin/python main.py
```

L2 must have the new SQLite store created at `visualai-orchestration/storage/brand_library.sqlite3` — happens automatically on first boot after this spec ships (see `data-model.md` §"L2 boot behavior").

Confirm all three are listening before each journey: `ss -tln | grep -E ':(3000|8089|8090) '`.

## Journey A — User Story 1: save a logo, reuse across modes

**Goal**: prove FR-001, FR-002, FR-005, FR-008, FR-009 end-to-end.

1. Open `http://localhost:3000` and click **Brand Library** in the sidebar.
2. Verify the page loads in under 1 second (SC-003) with empty-state copy if no logos saved.
3. Click **Upload logo**. Pick a transparent PNG (under the existing image-upload size cap, ≥ 480px short side per current validation).
4. Label it "Primary logo". Save.
5. Verify a card appears in the grid with the thumbnail, label, and an upload timestamp.
6. Open Mode 2 wizard (any subject). Reach the overlay step.
7. Verify the saved logo appears as a one-click thumbnail in the picker, alongside the "upload new" option.
8. Click the saved logo, finish the wizard, dispatch.
9. While the render runs, inspect the L1 `/api/generate` request body in the dev server log: it MUST contain `saved_logo_id` (and NOT `upload_path` for the logo).
10. Open the resulting MP4 once the render completes. Verify the logo appears composited per spec 009.
11. Open a Mode 5 wizard (or any other mode that has an overlay step once spec 009 expands). Verify the same saved logo is one-click pickable. The L3 `storage/uploads/...` directory should still contain ONE copy of the file (no duplicate from the second render's reference).

**Pass criteria** (mirrors SC-001, SC-002, FR-009):
- Logo appears in the picker for ≥ 1 mode after a single save.
- Render output carries the logo identically to a fresh per-render upload of the same file.
- Source file uploaded exactly once on disk.

## Journey B — User Story 2: save a brand color, use as overlay accent

**Goal**: prove FR-003, FR-006.

1. On the Brand Library page, click **Add color**.
2. Paste `#FF6B35` (or any valid 6-char hex). Label it "Brand orange". Save.
3. Verify the chip grid now shows a swatch with the label.
4. Open Mode 2 wizard. Reach the rectangle-overlay step (spec 009).
5. Verify the saved color appears as a labeled chip in the color picker.
6. Click the chip, set rectangle position + size, dispatch.
7. Inspect the resulting MP4. The rectangle MUST be exactly `#FF6B35`.

**Negative** (FR-003 invalid-hex):

1. On the Brand Library page, click **Add color**.
2. Paste `#XYZ123` (invalid).
3. Click save.
4. Verify the page shows an inline error (`invalid_hex` or similar) and does NOT persist the row.

## Journey C — User Story 3: brand voice as LLM context

**Goal**: prove FR-004, FR-010.

1. On the Brand Library page, in the "Brand Voice" textarea, paste:
   ```
   We build calm, judgment-free fitness tools for people over 50.
   ```
2. Click save. Verify the textarea retains the text after page reload.
3. Open Mode 2 wizard. Pick **Auto** script mode. Enter a subject like "morning stretch routine". Dispatch.
4. In the L3 dev log (or via a temporary `print` if not in dev mode), confirm the LLM system-prompt block contains the brand voice text.
5. Visually inspect the generated script preview in the wizard — the tagline phrasing should bias the output (e.g., "judgment-free" or "for people over 50" appearing in the copy is evidence; absolute presence is not strictly required).
6. Clear the textarea. Save (which is "delete" semantics for the singleton).
7. Re-dispatch the same Mode 2 Auto request. Confirm the LLM dispatch payload no longer contains brand-voice context — the L1 → L2 → L3 path is byte-identical to today's pre-020 behavior.

**Pass criteria** (mirrors SC-006):
- Brand voice text appears in the LLM prompt when saved.
- Brand voice text is absent from the LLM prompt when cleared.
- No regression: Mode 2 with no brand voice saved produces output indistinguishable from today.

## Tenant isolation smoke (SC-005)

This is operator-only since the demo bearer is single-tenant. To exercise:

1. Mint two demo bearers with different `tenant_id` claims (use `LAYER2_JWT_SIGNING_KEY` to sign).
2. Tenant A: upload a logo via the Brand Library. Note the returned `id`.
3. Tenant B: hit `GET /api/brand/logos`. Verify tenant B sees an empty list.
4. Tenant B: hit `DELETE /api/brand/logos/<tenant-A-logo-id>`. Verify 404 response.
5. Tenant B: dispatch a Mode 2 render with `saved_logo_id = <tenant-A-logo-id>`. Verify L2 returns 400 `saved_logo_not_found`.

## Reset between journeys

Each journey is idempotent. The SQLite file accumulates rows; to start fresh:

```sh
rm /root/dev/visualai/visualai-orchestration/storage/brand_library.sqlite3
# restart L2 — it recreates an empty DB
```

L3 disk uploads are NOT cleared by this — they are tenant-scoped and persist across `brand_library.sqlite3` resets. To clear those, manually `rm -rf storage/uploads/<tenant-id>/`.
