# Step 1 Debt — tracked principle relaxations

**Created**: 2026-04-21 (as part of the Step 1 Mode 2 MVP)
**Owner**: Layer 3 rendering engine (this repo)
**Authority**: [.specify/memory/constitution.md](.specify/memory/constitution.md) v1.1.0 + the 5-step build plan

Step 1 of the VisualAI 5-step build plan ships **Mode 2 (Short Marketing Video)** end-to-end on the existing MoneyPrinterTurbo engine before the full 5-layer architecture is in place. Doing this cleanly tonight requires consciously relaxing five constitution principles. Each relaxation is scheduled for repayment in a specific later step; this file is the single source of truth for what's owed and to whom.

| # | Principle | Step-1 relaxation | Repays in | Burn-down commit touches |
|---|---|---|---|---|
| ~~1~~ | ~~**I. Layer 3 Scope — Rendering Only**~~ | ~~Frontend calls Layer 3 directly because Layer 2 doesn't exist yet.~~ | **REPAID in spec 014 (Step 2)** | **DONE**: `../visualai-orchestration/` exists as separate FastAPI service; Layer 3 has JWT middleware (`app/middleware/jwt_auth.py`) that rejects requests not bearing a Layer-2-minted JWT; frontend's `layer2-client.ts` routes all API calls through `localhost:8080`. |
| ~~2~~ | ~~**III. Multi-Tenant Context Propagation**~~ | ~~Step-1 requests omit `tenant_id`, `user_id`, etc. No JWT middleware on video controllers.~~ | **REPAID in spec 014 (Step 2)** | **DONE**: `VideoParams.tenant_id` + `user_id` fields added; JWT middleware verifies HS256 tokens minted by Layer 2; `LAYER3_REQUIRE_TENANT_CONTEXT` flag enforces non-empty values in production; Loguru `contextualize()` propagates tenant fields to every log line emitted during a render. |
| 3 | **IV. External Asset Acceptance Over Direct API Calls** (PARTIAL) | Mode 2 B-roll is fetched directly from Pexels via the existing `app/services/material.py`. The constitution permits Pexels only inside Mode 5 (Faceless Channel Automation); here we stretch it to Mode 2 to avoid a `material.py` rewrite tonight. | **PARTIAL repay in spec 015 / Step 3 PR-A** — `material.py` now reads `pre_signed_clip_urls` from sidecar (FR-022) when Layer 2 populates it; Mode 5 retains its constitution-permitted direct Pexels carve-out. Mode 2 Auto + hybrid still call Pexels direct as residual debt; Layer 2 takes over the stock-fetch flow in **Step 3.5**. | DONE for the Mode-5 path; remainder: spec 015.5 wires Layer 2's Pexels fetcher + populates `pre_signed_clip_urls` for Mode 2 Auto. |
| ~~4~~ | ~~**V. Mode-Aware Rendering Contract**~~ | ~~Mode 2 prompt templates + search-term rules live inline inside `app/services/llm.py` (`generate_marketing_script` + the `mode == "short"` branches in `generate_script` and `generate_terms`). There is no `app/services/modes/` registry yet. `VideoParams.mode` accepts only `"faceless"` and `"short"`.~~ | **REPAID in spec 015 / Step 3 PR-A** | **DONE**: `app/services/modes/` package exists with `_interface.py` (Protocol), `__init__.py` (registry dispatcher), `short.py` (Mode 2), `faceless.py` (Mode 5). `VideoParams.mode` literal widened to `["short", "faceless", "product_shoot"]`. `task.py:generate_script` + `generate_terms` dispatch via `modes.pick(...)`. Constitution v1.1.0 amendment formalises the directory. |
| ~~5~~ | ~~**II. Surgical Fork Discipline** (Tier 1 Mode 2 quality fix)~~ | ~~`app/services/task.py` is edited with two one-line changes (pass `mode=params.mode` to `llm.generate_script` and `llm.generate_terms`). `task.py` is NOT one of the five permitted fork-surface files, which Principle II requires.~~ | **REPAID in spec 015 / Step 3 PR-A** | **DONE**: `task.py`'s mode-dispatch lines are now legitimate registry-dispatcher calls (`modes.pick(params.mode).generate_script(params)`). The dispatcher's home — `app/services/modes/` — is a documented fork-surface in constitution v1.1.0, so the touch no longer constitutes a Principle II violation. |
| 6 | **I. Layer 3 Scope** (PARTIAL — Principle I half repaid) + **III. Multi-Tenant Context** (PARTIAL — debt #2 retired in Step 2) | ~~The image-upload endpoint and per-render asset storage live in Layer 3 because Layer 2 doesn't exist yet.~~ Spec 014 routes upload requests through Layer 2 (Principle I half retires) and tenant-scopes the storage path to `storage/uploads/<tenant_id>/<uuid>.<ext>` (debt #2 retires for uploads). **Remaining**: Layer 3 still hosts the raw upload bytes; Layer 4's signed-URL store will retire that final piece. | **Step 3+** (Layer 4 signed-URL store) | When Layer 4's signed-URL store lands: replace the local `storage/uploads/` with pre-signed URLs from Layer 2; remove the upload endpoint from Layer 3 entirely; uploads become Layer 2/4 responsibilities only. |
| 7 | **SC-006 (spec 006)** — content moderation deferred | `MODERATION_REQUIRED=False` is the Step-1 default. The image-upload endpoint runs only a local heuristic (MIME validation + Pillow `verify()` + dimension guards); no real cloud moderation API. Spec 006's SC-006 ("100% rejection of an adversarial image test set") is explicitly unmet in Step 1. | **Public launch precondition (pre-Step 5)** | Wire a real cloud moderation provider (AWS Rekognition Moderation / Google Cloud Vision SafeSearch / Sightengine), set `MODERATION_REQUIRED=True`, run the adversarial test set, ship to public users only after green. |

## Principle II (Surgical Fork Discipline) scope boundary

Step 1 touches these files inside the five permitted fork-surface set:
- [`app/services/llm.py`](app/services/llm.py) — new `generate_marketing_script()` function; `generate_script` + `generate_terms` gained optional `mode` kwarg that branches to short-ad prompts when `mode == "short"`.
- [`app/services/material.py`](app/services/material.py) — defensive enum-value unwrap in `download_videos` concat-mode comparison.
- [`app/models/schema.py`](app/models/schema.py) — new optional `mode: Literal["faceless", "short"]` field on `VideoParams`; enum defaults for `video_aspect` and `video_concat_mode` changed from `.value` strings to enum instances.

Step 1 touches ONE file outside the fork-surface set (tracked as debt row #5 above):
- [`app/services/task.py`](app/services/task.py) — two one-line edits passing `mode=params.mode` to `llm.generate_script` and `llm.generate_terms`.

`ops/neon/migrations/` files added by feature 003 are Layer 4 DDL artifacts and fall under the constitution §Technology Constraints Database exception, not the Principle II surfaces.

## How the debt is tracked

- **Step 2** opens with a checklist task reading "burn down Step 1 debts #1 and #2" and MUST not close without updating this file.
- **Step 3** opens with a checklist task reading "burn down Step 1 debts #3 and #4" and MUST update this file to remove the repaid rows.
- When a row is repaid, strike it through (not delete) and add a `repaid in <commit sha>` note on the same line. The file preserves the full history of every temporary constitutional exception.

## When this file should be empty

Once all four rows are struck through, Step 1's debt is fully retired. At that point `STEP1_DEBT.md` SHOULD be deleted in the same commit that retires the final debt, with the commit message citing all four repayment references.

## Deferred-by-design (NOT principle relaxations)

Some functionality is intentionally absent from Step 1 not because we're cutting corners, but because the prerequisites don't exist yet. These are NOT principle relaxations — the constitution doesn't require them at Step 1 — but they ARE durable architectural commitments worth recording so future agents don't get confused about whether they should be built.

| Concern | Why absent at Step 1 | Where it lands | Spec |
|---|---|---|---|
| **Credit gating + token metering on Mode 2 renders** | Step 1 is single-user, no auth, no Layer 2. Without an authenticated customer record, there is no balance to gate against. The constitution-aligned home for credit logic is Layer 1 (frontend), but it requires a real `crm_member_id` from the Wix CRM webhook flow — VisualAI is pre-customer today. | **Step 4** (or earlier as a Step 1.5 increment when the first real customer signs up) | [Spec 008 — NexCognit Credit Gating Integration](specs/008-nexcognit-credit-gating/spec.md) (paused; resumes when any of three Resume conditions met) |

## Cross-references

- [VisualAI by NexCognit — Master Product Specification](VisualAI%20by%20NexCognit%20%E2%80%94%20Master%20Product%20Specification.md)
- [Constitution v1.0.2](.specify/memory/constitution.md)
- [Spec 001 — UI Style](specs/001-nexcognit-ui-style/spec.md) (frontend design system consumed by Step 1)
- [Spec 002 — Video Duration / Variations / Preview Gate](specs/002-video-duration-variations/spec.md) (preview-gate itself is Step 2+; Step 1 ships single-variation only)
- [Spec 008 — NexCognit Credit Gating Integration](specs/008-nexcognit-credit-gating/spec.md) (deferred-by-design; lands in Step 4 unless a real customer arrives sooner)
- [Spec 009 — Static Brand Overlays](specs/009-brand-overlays/spec.md) (specced; not yet implemented; continues debts #2 + #4 + #5)
- [Spec 010 — Music Track Control + Custom Uploads](specs/010-music-control/spec.md) (**implemented 2026-05-02**; uses existing `bgm_*` fields with no schema changes; continues debts #2 + #4 — does NOT touch debt #5 (no `task.py` edit) and does NOT touch `app/services/video.py` (Principle II preserved). The existing silent-fallback on BGM mixing failure at `app/services/video.py:546-557` is intentionally inherited as a v1 limitation — see spec 010 §Edge Cases.)
- [Spec 011 — BGM Audit Warning](specs/011-bgm-audit-warning/spec.md) (specced; not yet implemented; resolves spec 010's silent-fallback v1 limitation via observer pattern; designed to retire cleanly when Step 3's mode registry rewrites the audio path; continues debt #2)
- [Spec 012 — URL Scraping for Step 1 Input](specs/012-url-scraping/spec.md) (**implemented 2026-05-02**; **Layer 1 only** — zero MoneyPrinterTurbo touches; resolves the "agent silently treats URL as text" capability gap by scraping in Next.js server runtime and passing only enriched plain-text to MPT's `video_subject`. Continues debt #2 only — robots-cache and rate-limiter are process-global at v1, scope per-tenant in Step 2.)
- [Spec 013 — Polish Mode for Script Editor](specs/013-script-polish-mode/spec.md) (**implemented 2026-05-02**; resolves the "AI didn't reinvent the script" capability gap with a third script mode that takes a creator brief and rewrites it as hook/body/CTA. Touches three fork-surface files (`schema.py` for `script_mode` + `script_brief`, `llm.py` for new `polish_script`, `task.py` for the dispatch — third touch line continuing debt #5). Continues debt #4 (polish prompt inline in `llm.py`). Both repay together when Step 3's mode registry lands. Does NOT touch `material.py` / `voice.py` / `video.py`.)
- [Spec 014 — Orchestration Layer + Tenant Plumbing](specs/014-orchestration-tenant/spec.md) (**implemented 2026-05-03**; **retires debts #1 + #2 + Principle-I half of #6**; introduces Layer 2 as a separate FastAPI service in `../visualai-orchestration/`; adds JWT middleware + `tenant_id`/`user_id` fields on `VideoParams`; reroutes the wizard's 5 proxy routes through Layer 2; backfills `storage/uploads/` to a tenant-scoped layout. The `LAYER3_TRUST_LOCAL_UPSTREAM` flag preserves the upstream MoneyPrinterTurbo WebUI for local dev. Constitution Principle I + III flip from DEBT → PASS.)
- [5-step build plan](/Users/amraeid/.claude/plans/can-you-confirm-that-dapper-emerson.md)
