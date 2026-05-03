# Implementation Plan: Modes 1 + 5 + Mode Registry + Layer 2.5 Image Routing (Step 3)

**Branch**: `015-modes-1-5-registry` | **Date**: 2026-05-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-modes-1-5-registry/spec.md`

## Summary

Step 3 turns the dashboard from "Mode 2 only" into "three live modes" by activating **Mode 5 (Faceless Channel)** and **Mode 1 (Product Shoot Generator)**, while paying down three architectural debts:

1. **`app/services/modes/`** lands as a real Python package (each mode = one module exporting a stable `Mode` interface). `task.py`'s mode dispatch becomes single-line registry calls. Burns debts #4 + #5.
2. **`app/services/material.py`** rewrites to read pre-signed asset URLs from the per-task `visuals.json` sidecar that Layer 2 writes. Pexels + Pixabay direct calls remain ONLY in the Mode 5 code path (constitution Principle IV exception). Mode 2 Auto path migrates to the new pre-signed URL flow; Mode 2 hybrid path stays direct as a smaller residual debt #3 (scheduled for Step 3.5).
3. **Layer 2.5** materialises as a new `app/router/` package inside the orchestration repo. First delivery: image-generation routing (NanoBanana Pro / equivalent) for Mode 1. Video-generation routing (Veo / Kling / Luma) is reserved (`router/video.py` slot left empty) for a follow-up.

Constitution v1.1.0 amendment lands in the same PR: adds Mode 1 + Mode 5 to the actively-implemented column, formalises `app/services/modes/` as a documented surface, and strikes through STEP1_DEBT.md rows #4, #5, and the auto-mode half of #3.

The plan recommends slicing the work across **two PRs** (PR-A: Mode 5 + registry + material.py rewrite; PR-B: Mode 1 + Layer 2.5) so neither lands a 3000-line diff. Both target the same branch (`015-modes-1-5-registry`); PR-A merges first and PR-B rebases on top.

## Technical Context

**Language/Version**:
- Layer 3 (this repo): Python 3.11/3.12 (unchanged).
- Layer 2 (`../visualai-orchestration/`): Python 3.11/3.12 (unchanged).
- Layer 1 (`../visualai-frontend/`): TypeScript / Next.js 16 / React 19 (unchanged).

**Primary Dependencies**:
- Layer 3: existing only — no new runtime deps. The `app/services/modes/` package is pure Python (Mode interface + per-mode modules). `material.py` rewrite uses existing `httpx` (transitive) + `requests` (existing) for downloading from pre-signed URLs.
- Layer 2: **new** — image-generation HTTP client (uses existing `httpx.AsyncClient`); optional `Pillow` for contact-sheet slicing if the chosen provider returns a 3×2 sheet (already available transitively).
- Layer 1: existing only — `<input type="file">` + native FormData + `fetch`. No new deps.

**Storage**:
- Layer 3: existing filesystem (`storage/uploads/<tenant_id>/<uuid>.<ext>`, `storage/tasks/<task_id>/`). No new directories.
- Layer 2: **NEW** — `storage/uploads/<tenant_id>/` (mirror of Layer 3 — Layer 2 holds the canonical upload bytes, Layer 3 reads via pre-signed URLs that point into Layer 2's mount). Layer 2 also gains `storage/tasks/<task_id>/` for Mode 1 product-shoot output images (these never go to Layer 3 — Mode 1 is a Layer-2-only flow).
- Pre-signed URL format (Step 3): `http://<layer2-host>:8088/_signed/<sig>/<tenant_id>/<uuid>.<ext>?expires=<unix>`. Layer 2 mounts a static-file server on `/_signed/` with HMAC signature validation. Step 4 replaces this with a real CDN signed-URL store.

**Testing**:
- Layer 3: pytest existing patterns. New `test/services/modes/test_registry.py` covering the registry dispatcher + per-mode modules. `test_material_pre_signed_urls.py` covering the pre-signed URL flow.
- Layer 2: pytest with `respx` for mocking the upstream image-generation API. New `tests/contract/test_product_shoots.py` + `tests/router/test_image_router.py` + `tests/routes/test_pre_signed.py`.
- Layer 1: Vitest for new wizard helpers + proxy routes.

**Target Platform**: Same as Steps 1+2 — Python 3.11/3.12 on Linux/Docker for backend services; Next.js on Vercel/Node for Layer 1.

**Project Type**: Multi-tier service architecture (3 tiers + 1 sub-tier). Layer 2.5 is logically inside Layer 2's process boundary in Step 3 (a new package, not a separate service); a future split into its own service is possible but not in scope.

**Performance Goals**:
- SC-002: Mode 1 generates 6 images within 60s for 95th percentile. Realistically: NanoBanana Pro returns a contact sheet in ~30s + Pillow slicing ~1s + 6 file writes ~1s + HTTP overhead ~1s = ~33s typical, comfortably under SC-002.
- SC-003: Mode 2 zero regression — render time within ±5% of pre-Step-3.
- Mode 5: same as Mode 2 Auto today (~60-90s end-to-end).
- Layer 2.5 image router latency: ≤ 2s overhead vs direct provider call (just routing + JWT mint + URL signing).

**Constraints**:
- Zero new Layer 3 runtime deps (Principle II spirit — minimise upstream-rebase risk).
- `app/services/modes/` modules MUST be stateless (worker-thread safety; renders run concurrently).
- `material.py` rewrite is a refactor — must preserve existing public function signatures (`download_videos`, `save_video`) so test fixtures + non-Mode-2 upstream MPT callers don't break.
- `task.py` simplification removes the existing 3-line debt #5 dispatch but the file CONTINUES to exist (it's the orchestrator). Debt #5 retires because the dispatch logic moves to the registry.
- Pre-signed URLs in Step 3 are short-lived (15-min expiry, matching JWT) and HMAC-signed. Step 4 replaces with CDN signed URLs.
- Layer 2.5 image router is synchronous from Layer 2's perspective (Layer 2 awaits the response, returns to Layer 1). Async / webhook-based completion is a Step 4+ concern when generation latency exceeds frontend polling tolerance.

**Scale/Scope**:
- Step 3 still single-user (debt #2 burned in Step 2 but the demo tenant is hardcoded; multi-tenant data isolation lands in Step 4).
- Per-tenant Mode 1 generation cost: estimated $0.04-0.10 per 6-image batch via NanoBanana Pro at ~$0.01/image. Cost tracking is log-only in Step 3 (FR-029); hard limits land in Step 4.
- Mode 5 + Mode 2 retain Pexels free-tier quotas (200 req/h baseline).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (see end of plan).*

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | **PASS** | Mode 1's whole pipeline lives in Layer 2 + Layer 2.5; Layer 3 has zero role. Mode 5 lives in Layer 3 as a render task (its constitution-permitted home). The pre-signed URL pattern keeps Layer 3 receiving asset URLs from Layer 2, never bytes directly (except where the existing upload endpoint inherits from Step 2's debt #6). |
| **II. Surgical Fork Discipline** | **PASS-with-amendment** | Existing fork-surface files touched: `schema.py`, `material.py`, `llm.py`, `task.py`. The new `app/services/modes/` directory is formalised by **constitution v1.1.0 amendment** (adds modes registry to documented surface). Without the amendment this would be a new debt; with it, the directory is a first-class part of the fork structure. **Burns debt #5** (task.py touch becomes registry-dispatch — single line, structurally aligned with mode registry). |
| **III. Multi-Tenant Context Propagation** | **PASS** | Step 2's JWT middleware applies to all new endpoints. Mode 1's Layer 2 endpoint inherits the demo bearer + tenant context; Layer 2.5's outbound calls log `tenant_id` per FR-029. |
| **IV. External Asset Acceptance Over Direct API Calls** | **PASS-improving** | Mode 5 IS the constitution-permitted Mode 5 exception (Pexels for faceless content). Mode 2 Auto path migrates to Layer 2 pre-signed URLs — the bulk of debt #3 retires. Mode 2 hybrid path's Pexels + Pixabay direct calls remain as a smaller residual debt awaiting Step 3.5. Layer 2.5 owns ALL outbound generation API calls (NanoBanana Pro for Mode 1) — Layer 3 never calls generation APIs. |
| **V. Mode-Aware Rendering Contract** | **PASS** | `app/services/modes/` registry lands as the canonical mode dispatcher. Each mode is a module with stable interface. Adding Mode 6 = new module + literal widen + constitution amendment. **Burns debt #4** completely. |

**Gate verdict**: PASS-with-justified-amendment. The constitution amendment to v1.1.0 is the formal mechanism; without it, the new `app/services/modes/` directory would be a Principle II violation. With it, the structure is constitution-aligned.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `app/services/modes/` directory (new, outside Step 1's documented 5 fork-surface files) | Principle V is NON-NEGOTIABLE — modes MUST live in `app/services/modes/` per the constitution's existing wording. The directory has been TODO since Step 1; its absence has been the reason debts #4 + #5 stayed open. Constitution v1.1.0 amendment formalises the directory; PR includes the amendment. | Inline mode dispatch (current state, debt #4): leaves debts #4 + #5 open indefinitely; blocks Principle V from ever flipping to PASS. Single mega-file `modes.py`: scaling problem at Mode 5+; loses the per-mode test isolation. Modes-as-classes-only with no package: fights Python's import / discoverability story. |

The constitution amendment is documented in `research.md` R1 with the exact diff to `.specify/memory/constitution.md`.

## Project Structure

### Documentation (this feature)

```text
specs/015-modes-1-5-registry/
├── plan.md              # This file
├── research.md          # Phase 0 — provider, registry interface, pre-signed URLs, slicing, contact sheet, faceless dispatch
├── data-model.md        # Phase 1 — Mode interface, Product Shoot Generation, Pre-signed URL, registry table
├── quickstart.md        # Phase 1 — manual end-to-end across all 3 modes
├── contracts/
│   ├── modes-registry-interface.md       # Layer 3 — Mode interface every mode module exports
│   ├── material-pre-signed-urls.md       # Layer 3 — sidecar shape for pre-signed URLs vs direct Pexels
│   ├── layer2-product-shoots-api.md      # Layer 2 — POST /api/v1/product-shoots endpoint
│   ├── layer25-image-router.md           # Layer 2.5 — generate_studio_photos(...) + provider abstraction
│   └── frontend-mode-1-5-wizards.md      # Layer 1 — new wizard routes + dashboard activation
├── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
└── checklists/
    └── requirements.md  # already complete from /speckit-specify
```

### Source Code

**Layer 3 (this repo) — touched files**:

```text
app/
├── services/
│   ├── modes/                       # NEW — formalised by constitution v1.1.0
│   │   ├── __init__.py              # exports `pick(name) -> Mode`, `register(mode)`, type stubs
│   │   ├── _interface.py            # the abstract Mode interface (Protocol)
│   │   ├── short.py                 # Mode 2 — moves marketing-script + setting-tag + hybrid logic out of llm.py
│   │   └── faceless.py              # Mode 5 — generic-stock dispatch + topic-driven term generation
│   │   # NOTE: product_shoot.py NOT here — Mode 1 doesn't dispatch through Layer 3
│   ├── llm.py                       # SHRINK — Mode 2 prompts move to modes/short.py; llm.py keeps generic LLM helpers + polish_script
│   ├── material.py                  # REWRITE — sidecar reads pre_signed_clip_urls; Pexels/Pixabay gated to mode == "faceless"
│   └── task.py                      # SIMPLIFY — generate_script + generate_terms become 1-line registry dispatchers; debt #5 retires
└── models/
    └── schema.py                    # WIDEN — VideoParams.mode literal: ["faceless", "short", "product_shoot"]

.specify/memory/
└── constitution.md                  # AMEND to v1.1.0 — adds modes/ to documented surface; notes Modes 1+5 as actively implemented

STEP1_DEBT.md                        # UPDATE — strike rows #3 (Auto path), #4, #5

test/services/
├── modes/                           # NEW
│   ├── __init__.py
│   ├── test_registry.py             # Mode dispatcher: pick("short") → short module; pick("invalid") → KeyError → 422
│   ├── test_short.py                # Mode 2 module behaviour matches pre-Step-3 behaviour byte-for-byte
│   └── test_faceless.py             # Mode 5 module's term generation, aspect ratio, etc.
└── test_material_pre_signed_urls.py # NEW — material.py reads sidecar URLs, falls back to Pexels for Mode 5 only
```

**Layer 2 (`../visualai-orchestration/`) — touched + new files**:

```text
app/
├── router/                          # NEW — Layer 2.5
│   ├── __init__.py                  # exports `generate_studio_photos(...)`
│   ├── image.py                     # Generic image-router orchestration + contact-sheet slicing
│   └── _provider_nanobanana.py      # Provider-specific adapter (replaceable; one of several possible providers)
├── routes/
│   ├── product_shoots.py            # NEW — POST /api/v1/product-shoots (Mode 1 entrypoint)
│   ├── pre_signed.py                # NEW — GET /_signed/<sig>/<tenant>/<uuid>.<ext>?expires=<unix>
│   └── (existing: videos, tasks, uploads, scripts) — videos.py extended to recognise mode="faceless"
├── auth/
│   └── pre_signer.py                # NEW — HMAC URL signer + verifier
└── (existing: main.py, config.py, etc.)

storage/
├── uploads/<tenant_id>/<uuid>.<ext> # NEW dir — Layer 2 holds canonical bytes; Layer 3 reads via pre-signed URLs
└── tasks/<task_id>/                 # NEW — Mode 1 generation outputs (6 image files)

tests/
├── router/
│   └── test_image.py                # NanoBanana mock + contact-sheet slicing
├── routes/
│   ├── test_product_shoots.py
│   └── test_pre_signed.py           # signature validation, expiry, tenant scoping
└── (existing tests)

.env.example                         # add LAYER25_IMAGE_PROVIDER, LAYER25_NANOBANANA_API_KEY
```

**Layer 1 (`../visualai-frontend/`) — touched + new files**:

```text
src/app/
├── modes/
│   ├── faceless-channel/
│   │   └── page.tsx                 # NEW — wizard (topic + voice + music)
│   └── product-shoot/
│       └── page.tsx                 # NEW — wizard (single image + optional description)
├── api/
│   ├── product-shoot/
│   │   └── route.ts                 # NEW — proxy to Layer 2's POST /api/v1/product-shoots
│   └── (existing /api/* — small extension to /api/generate to accept mode="faceless")
└── page.tsx                         # EXTEND — Mode 1 + Mode 5 cards become clickable; "Coming in Step 3" badges removed

src/lib/
└── product-shoot.ts                 # NEW — types + helpers (analogous to spec 006's visuals-mode.ts)

tests/
└── product-shoot.test.ts            # Vitest helper coverage
```

**Structure Decision**: Three-tier with Layer 2.5 as a new sub-package inside Layer 2 (not a separate service). The package boundary documents Layer 2.5's responsibility but the deployment unit stays a single FastAPI service. If Layer 2.5's image-generation latency becomes a bottleneck (Step 4+), the split into a separate service is mechanical — every public function in `app/router/` already has a clean interface.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `app/services/modes/` (new directory in Layer 3) | Constitution Principle V is NON-NEGOTIABLE; the registry has been the planned destination since Step 1 (debt #4). v1.1.0 amendment formalises it. | All alternatives discussed in the constitution-check table above. |
| `storage/uploads/` mirror in Layer 2 | Layer 2 must hold the canonical upload bytes for the pre-signed-URL pattern to work; Layer 3 can no longer be the file-of-record. | Keeping storage in Layer 3 only: violates Principle I (uploads are user data, not rendering data). Single-DB store: Step 4 work, doesn't fit Step 3's scope. |
| Layer 2.5 inside Layer 2 (not separate service) | Step 3 single-user; deployment overhead of a separate service isn't justified. The package boundary is in code; deployment can split later when scale demands. | Separate visualai-router repo: 3rd new repo this quarter; deployment story expands; no scaling pressure yet. |

All justifications align with "do the simplest constitution-compliant thing for Step 3, leave architectural seams for Step 4+ scaling."

## Constitution Re-check (post-Phase 1)

*Re-evaluated after data-model.md + contracts generation.*

- Principle I: PASS — re-confirmed. Mode 1 generation lives in Layer 2.5; pre-signed URLs cross the Layer 2 → Layer 3 boundary cleanly; Mode 5's direct Pexels call is the constitution's permitted exception.
- Principle II: PASS-with-amendment — `app/services/modes/` is formalised in constitution v1.1.0. The new directory is the only addition outside the original 5 fork-surface files; documented + tracked.
- Principle III: PASS — every Mode 1 + Mode 5 endpoint inherits Step 2's JWT middleware; tenant context propagates.
- Principle IV: PASS-improving — Mode 5 is the permitted exception; Mode 2 Auto path retires to Layer 2 pre-signed URLs; Mode 2 hybrid path remains as residual debt #3 (smaller scope, scheduled for Step 3.5).
- Principle V: PASS — the registry IS the contract; debt #4 retires; debt #5 retires (task.py simplifies to single-line registry dispatch).

**STEP1_DEBT.md row updates after Step 3 lands**:
- Row #3 (External Asset Acceptance): **partially struck** — Mode 2 Auto retires; Mode 5 is the exception; Mode 2 hybrid is residual.
- Row #4 (Mode-Aware Rendering Contract): **struck through** — registry lands.
- Row #5 (Surgical Fork — task.py edit): **struck through** — task.py simplifies; registry-dispatch is the legitimate touch.
- Row #6 (Layer-3 upload carve-out): unchanged this round (storage retires in Step 4).
- Row #7 (Moderation deferred): unchanged (public-launch precondition).

Constitution version bumps to v1.1.0 in this PR.
