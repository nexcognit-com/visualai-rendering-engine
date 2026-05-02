# Implementation Plan: Orchestration Layer + Tenant Plumbing (Step 2)

**Branch**: `014-orchestration-tenant` | **Date**: 2026-05-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-orchestration-tenant/spec.md`

## Summary

Stand up Layer 2 (the **VisualAI Orchestration API**) as a new FastAPI service in a sibling repo `../visualai-orchestration/`. Layer 2 is the front door for the wizard: it authenticates incoming requests via a static demo bearer token (Step 2 single-user), mints a short-lived HMAC-SHA256 JWT carrying tenant context, and forwards to Layer 3. Layer 3 (this repo) gains JWT-verification middleware on its video controllers, makes `tenant_id` + `user_id` required fields on `VideoParams`, and binds tenant context into Loguru for all downstream logs and audit entries. The Next.js wizard reroutes from direct Layer 3 calls (`localhost:8090`) to Layer 2 (`localhost:8080`).

This plan retires `STEP1_DEBT.md` rows #1 (Layer 3 Scope) and #2 (Multi-Tenant Context) — both go from DEBT to PASS in the constitution check. Storage paths under `storage/uploads/` migrate to `storage/uploads/<tenant_id>/<uuid>.<ext>` so Step 4's per-tenant data isolation has a clean home to land in.

The architecture is forward-compatible: when NextAuth + Wix CRM integration lands in Step 4, the static demo bearer is replaced with NextAuth-issued tokens at the Layer 2 boundary without API-shape changes to Layer 3.

## Technical Context

**Language/Version**:
- Layer 2 (new repo): Python 3.11/3.12 (matches Layer 3 + constitution).
- Layer 3 (this repo): Python 3.11/3.12 (unchanged).
- Layer 1 (frontend, sibling repo): TypeScript / Next.js 16 / React 19 (unchanged).

**Primary Dependencies**:
- Layer 2: FastAPI + uvicorn + httpx (forwarding) + PyJWT (token mint/verify) + python-multipart (multipart proxying).
- Layer 3: FastAPI (existing) + PyJWT (new — for verification middleware). No other new deps.
- Layer 1: native `fetch` (existing). No new deps.

**Storage**:
- Layer 2: stateless — no DB, no filesystem state. Demo tenant context comes from env vars.
- Layer 3: existing filesystem (`storage/uploads/<uuid>.<ext>` migrates to `storage/uploads/<tenant_id>/<uuid>.<ext>`; `storage/tasks/<task_id>/` unchanged).

**Testing**:
- Layer 2: pytest + httpx async client + FastAPI TestClient. JWT mint/verify mocked via fixtures.
- Layer 3: pytest (existing patterns). New `test/middleware/test_jwt_auth.py` for the JWT middleware. Existing tests gain the JWT header in their fixtures.
- Layer 1: Vitest (existing). No new tests beyond updating the proxy stubs to point at Layer 2 mock.

**Target Platform**: Same as Layer 3 — Python 3.11/3.12 on Linux/Docker for backend services; Next.js on Vercel/Node for Layer 1.

**Project Type**: Multi-tier service architecture (Layer 1 frontend + Layer 2 orchestration + Layer 3 rendering). Each tier is a separate git repository.

**Performance Goals**:
- SC-003: Layer 2 forwarding adds ≤ 2 s to a Mode 2 render's wall time. Realistically ≤ 100 ms in steady state (loopback HTTP + JWT mint + small JSON forward).
- JWT mint: HMAC-SHA256 should be < 1 ms per request.
- JWT verify: same — < 1 ms.

**Constraints**:
- Layer 2 must NOT introduce a database (Step 2 is stateless infrastructure).
- Layer 3's existing single-user demo path must remain runnable for `webui/Main.py` via the `LAYER3_TRUST_LOCAL_UPSTREAM` flag (FR-017).
- Production guard: refuse to start with placeholder secrets if `LAYER2_ENV=production` (FR-018).
- No Layer 2.5 (Dynamic Model Router) work — that's Step 3.
- No NextAuth, no Neon, no credit ledger — those are Step 4.

**Scale/Scope**:
- Step 2 single-user. Realistically 1 concurrent render at a time (the existing Layer 3 task manager is in-memory and serial-ish).
- Layer 2 sized for ~10 req/s in dev. Production scale follows Layer 3's GPU-bound bottleneck.
- Multi-tenant scaling (real concurrent tenants) is a Step 4+ concern.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (see end of plan).*

| Principle | Status | Notes |
|---|---|---|
| **I. Layer 3 Scope — Rendering Only (NON-NEGOTIABLE)** | **BURNED → PASS** | Step 2's whole point. Layer 3 stops accepting direct frontend calls (FR-008/009/010); Layer 2 is now the front door. Debt #1 retires. |
| **II. Surgical Fork Discipline** | **PASS** | Layer 3 changes touch fork-surface files only: `app/models/schema.py` (gain tenant fields), `app/controllers/v1/video.py` + `llm.py` + `uploads.py` (JWT middleware via FastAPI dependency on the existing controllers — additive). New `app/middleware/jwt_auth.py` is a new file in the existing `app/` tree; allowed because it's NOT inside the rendering pipeline (`app/services/`) and is needed for the constitution-mandated JWT verification (Principle III). NO `task.py` / `material.py` / `voice.py` / `video.py` / `subtitle.py` / `llm.py-services` edits. |
| **III. Multi-Tenant Context Propagation** | **BURNED → PASS** | `tenant_id` + `user_id` become required on `VideoParams` (FR-011). JWT middleware enforces them (FR-008). Loguru `bind()` propagates to all downstream log calls (FR-012). Audit entries get `tenant_id` (FR-013). Debt #2 retires. |
| **IV. External Asset Acceptance Over Direct API Calls** | **PARTIAL** (still in debt #3) | Step 2 doesn't rewrite `material.py`. Pexels + Pixabay calls from Layer 3 stay direct (debt #3 unchanged). Layer 2 does NOT route generation APIs in Step 2 — that's Layer 2.5 / Step 3. |
| **V. Mode-Aware Rendering Contract** | **UNCHANGED** | No `app/services/modes/` registry work. Debt #4 stays. |

**Gate verdict**: PASS — debts #1 + #2 burned; debts #3 + #4 + #5 unchanged from Step 1's status. New row #6 (spec 006 upload-Layer-3 carve-out) becomes partially repaid: uploads now route through Layer 2 (Principle I burned for uploads too), but storage location remains `storage/uploads/` until Layer 4's signed-URL store lands.

**Complexity tracking**: one new file outside the strict five fork-surface set:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `app/middleware/jwt_auth.py` (new file) | Constitution Principle III explicitly requires JWT middleware on Layer 3's video controllers. The middleware must intercept ALL requests before Pydantic parsing to inject tenant context into the body — this is structurally incompatible with implementing the check inline in each controller (would duplicate ~30 lines × 5 endpoints) or via Pydantic validators (which run too late to enforce auth). | Inline checks: code duplication × 5 endpoints; FastAPI Depends-only: doesn't have access to mutate the request body before Pydantic; Layer 2 only: leaves Layer 3 unprotected against direct calls. |

The `app/middleware/` directory is a new addition outside the documented fork-surface set; this is justified by Principle III's NON-NEGOTIABLE wording AND by the fact that middleware is a clean architectural slot (FastAPI's `Depends` + middleware mechanics) that doesn't risk upstream-rebase conflicts.

## Project Structure

### Documentation (this feature, in this repo)

```text
specs/014-orchestration-tenant/
├── plan.md              # This file
├── research.md          # Phase 0 — JWT scheme, Loguru context, Layer 2 framework
├── data-model.md        # Phase 1 — JWT claims, VideoParams extension, tenant context
├── quickstart.md        # Phase 1 — manual end-to-end verification
├── contracts/           # Phase 1
│   ├── layer2-api.md              # Public Layer 2 endpoints (frontend ↔ Layer 2)
│   ├── layer2-to-layer3.md        # Forwarding contract (JWT shape, header, body)
│   ├── layer3-jwt-middleware.md   # Verification semantics + error codes
│   └── frontend-layer2-wiring.md  # Wizard env vars + bearer header
├── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
└── checklists/
    └── requirements.md  # Already complete from /speckit-specify
```

### Source Code

**Layer 2 — new sibling repo (`../visualai-orchestration/`)**:

```text
visualai-orchestration/
├── app/
│   ├── main.py                     # FastAPI app + uvicorn entry
│   ├── config.py                   # env-var loading + production-guard checks
│   ├── auth/
│   │   ├── bearer.py               # Demo-bearer validation
│   │   └── jwt_issuer.py           # JWT mint with tenant context claims
│   ├── routes/
│   │   ├── videos.py               # POST /api/v1/videos forwarder
│   │   ├── tasks.py                # GET /api/v1/tasks/{task_id} forwarder
│   │   ├── uploads.py              # POST /api/v1/uploads/image + /audio forwarders (multipart)
│   │   └── scripts.py              # POST /api/v1/scripts/polish-preview forwarder
│   ├── forwarder.py                # Shared httpx client + Layer 3 URL config
│   └── tenant_context.py           # Demo-tenant constants + future-extensible builder
├── tests/
│   ├── contract/
│   │   ├── test_videos_forward.py
│   │   ├── test_tasks_forward.py
│   │   ├── test_uploads_forward.py
│   │   ├── test_scripts_forward.py
│   │   └── test_auth.py            # Bearer validation + JWT mint
│   ├── integration/
│   │   └── test_e2e_demo_render.py # Full Layer 2 → mock Layer 3 round-trip
│   └── conftest.py                 # FastAPI TestClient + httpx mock fixtures
├── pyproject.toml                  # FastAPI + uvicorn + httpx + PyJWT + python-multipart
├── .env.example                    # LAYER2_DEMO_BEARER, LAYER2_JWT_SIGNING_KEY, LAYER3_BASE_URL, etc.
├── README.md                       # Quickstart + dev setup
└── main.py                         # python main.py entry mirroring Layer 3's convention
```

**Layer 3 (this repo) — touched files only**:

```text
app/
├── middleware/                     # NEW directory (one allowed file outside fork-surface)
│   ├── __init__.py
│   └── jwt_auth.py                 # FastAPI dependency that verifies JWT + injects tenant context
├── models/
│   └── schema.py                   # EXTEND — VideoParams.tenant_id + user_id required
└── controllers/v1/
    ├── video.py                    # EXTEND — wire JWT dependency on /videos + /tasks routes
    ├── llm.py                      # EXTEND — wire JWT dependency on /scripts/polish-preview
    └── uploads.py                  # EXTEND — wire JWT dependency on /uploads/image + /audio

storage/uploads/                    # PATH MIGRATION
└── <tenant_id>/                    # NEW — was flat <uuid>.<ext>; now tenant-prefixed
    └── <uuid>.<ext>

test/
├── middleware/
│   └── test_jwt_auth.py            # NEW — middleware unit tests
└── controllers/                    # UPDATE existing fixture helpers to add Authorization header
    ├── test_image_upload.py        # gain JWT-bearing fixture
    └── test_uploads_audio.py       # same

STEP1_DEBT.md                       # UPDATE — strike rows #1 + #2; partially strike row #6
```

**Layer 1 (sibling `visualai-frontend/`) — touched files only**:

```text
visualai-frontend/
├── .env.example                    # UPDATE — NEXT_PUBLIC_LAYER2_URL replaces LAYER3_URL
├── src/app/api/
│   ├── generate/route.ts           # EXTEND — point at LAYER2_URL + send Authorization: Bearer header
│   ├── status/[taskId]/route.ts    # same
│   ├── upload-image/route.ts       # same
│   ├── upload-audio/route.ts       # same
│   └── polish-preview/route.ts     # same
└── tests/                          # UPDATE — mock Layer 2 endpoints (was Layer 3)
```

**Structure Decision**: Three-tier architecture. Layer 2 is a NEW sibling repo (not a subdirectory of this one) per the constitution's Layer 3 Scope principle and the deployment shape goal (independent scaling). Layer 3 changes are surgical: one new file (`app/middleware/jwt_auth.py`) plus extensions to fork-surface files. Layer 1 changes are env-var + header swaps in existing proxy routes — no new components or pages.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `app/middleware/jwt_auth.py` (new file outside the 5 fork-surface files) | Constitution Principle III is NON-NEGOTIABLE; JWT verification must intercept requests before Pydantic parsing to inject tenant context. The five fork-surface files don't include a middleware location — `app/services/` is rendering-pipeline, `app/controllers/` is per-route handlers, `app/models/` is Pydantic schemas. Middleware needs its own slot. | Inline per-controller: 30+ duplicate lines × 5 endpoints. Pydantic validator: runs after auth would be too late; can't reject early. Pure dependency-injection-only without middleware mutation: doesn't have access to mutate the request body in the way needed for clean tenant-context injection without conflicts with the existing wire shapes. |
| `app/middleware/__init__.py` (new directory) | Required to hold the new file. Empty package marker, zero behavioral content. | N/A. |

Both additions are inside `app/` (the existing fork tree) but in a new `middleware/` subdirectory. They do NOT touch `app/services/` (rendering pipeline) or any other fork-surface file. Upstream-rebase risk: minimal — a new top-level subdirectory of `app/` is unlikely to conflict with upstream MoneyPrinterTurbo additions, which historically extend `app/services/` and `app/controllers/`.

## Constitution Re-check (post-Phase 1)

*Re-evaluated after data-model.md + contracts generation.*

- Principle I: PASS — Layer 3 hardens against direct calls; only Layer 2's signed JWTs are accepted. Debt #1 retires.
- Principle II: PASS-with-justified-complexity — `app/middleware/` is the one new directory; complexity tracking documents the rationale.
- Principle III: PASS — `tenant_id` + `user_id` propagate via JWT → middleware → request state → VideoParams → Loguru `bind()` → audit log. Debt #2 retires.
- Principle IV: UNCHANGED (debt #3 stays — Pexels/Pixabay still called direct from Layer 3; Layer 2.5 routing in Step 3).
- Principle V: UNCHANGED (debt #4 stays).

No new debt introduced. New STEP1_DEBT.md row updates:
- Row #1 (Layer 3 Scope): **struck through** with this PR's commit sha.
- Row #2 (Multi-Tenant Context): **struck through** with this PR's commit sha.
- Row #6 (spec 006 upload Layer-3 carve-out): partially struck — Layer-3-Scope half retires (uploads route through Layer 2); the storage-location half (still in `storage/uploads/`) remains until Step 3+ when Layer 4's signed-URL store lands.
