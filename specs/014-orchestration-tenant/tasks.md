# Tasks: Orchestration Layer + Tenant Plumbing (Step 2)

**Feature**: 014-orchestration-tenant
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)
**Date**: 2026-05-03

## Overview

Three user stories, prioritized:
- **US1 (P1)**: Render through Layer 2 → Layer 3 with JWT. MVP — the entire point of Step 2.
- **US2 (P1)**: Tenant context propagates through logs + audit log. Falls largely out of US1's plumbing.
- **US3 (P2)**: Backward-compat for upstream MPT WebUI via `LAYER3_TRUST_LOCAL_UPSTREAM` flag.

Tests are required (mirroring spec 006/013 precedent).

Three repos involved:
- **Layer 2** (NEW): `../visualai-orchestration/`
- **Layer 3** (this repo): `MoneyPrinterTurbo/`
- **Layer 1** (frontend, sibling): `../visualai-frontend/`

---

## Phase 1: Setup

- [ ] T001 Scaffold the Layer 2 repo at `../visualai-orchestration/`. Create directory + `git init` + `pyproject.toml` (Python 3.11/3.12, FastAPI, uvicorn, httpx, PyJWT, python-multipart, python-ulid, pytest dev deps) + `main.py` entry + `.env.example` + `.gitignore` (Python defaults + `.env`). Mirror Layer 3's `main.py → app.asgi:get_application()` pattern for consistency.

- [ ] T002 [P] Add `PyJWT>=2.8` to Layer 3's `requirements.txt` (or `pyproject.toml` if upstream uses it). Run `pip install PyJWT` in `.venv`. Verify `python -c "import jwt; print(jwt.__version__)"`.

- [ ] T003 [P] Create Layer 3 `.env.example` (or update existing) with:
    ```
    LAYER2_JWT_SIGNING_KEY=changeme-generate-via-openssl-rand-hex-32
    LAYER3_TRUST_LOCAL_UPSTREAM=false
    LAYER3_REQUIRE_TENANT_CONTEXT=false
    LAYER3_ENV=development
    ```
    Document in repo root `README.md` that prod must override these.

- [ ] T004 [P] Update Layer 1 `.env.example` and `.env.local`:
    ```
    NEXT_PUBLIC_LAYER2_URL=http://localhost:8080
    NEXT_PUBLIC_LAYER2_DEMO_BEARER=demo-bearer-replace-in-production
    ```
    Remove the old `NEXT_PUBLIC_LAYER3_URL` (no longer needed; Layer 1 doesn't talk to Layer 3 directly).

---

## Phase 2: Foundational

These tasks unblock all user stories.

- [ ] T005 Generate a real `LAYER2_JWT_SIGNING_KEY` via `openssl rand -hex 32`. Store the same value in (a) Layer 2's `.env`, (b) Layer 3's `.env`. Verify both services read it on startup.

- [ ] T006 [P] Layer 2 — implement `app/config.py` reading env vars: `LAYER3_BASE_URL`, `LAYER2_DEMO_BEARER`, `LAYER2_JWT_SIGNING_KEY`, `LAYER2_DEMO_TENANT_ID`, `LAYER2_DEMO_USER_ID`, `LAYER2_ENV`. Pydantic-settings or simple `os.getenv` — both fine.

- [ ] T007 [P] Layer 2 — implement `app/auth/bearer.py` with `verify_demo_bearer(request: Request)` FastAPI dependency. Constant-time compare via `hmac.compare_digest()`. Raises HTTP 401 with typed error_code on missing/invalid bearer per [contracts/layer2-api.md](contracts/layer2-api.md) §Authentication.

- [ ] T008 [P] Layer 2 — implement `app/auth/jwt_issuer.py` with `mint_jwt(tenant_id, user_id) → (token: str, jti: str)`. HS256, 15-min exp, ULID jti. Tests for token decodability + claim correctness using a test fixture key.

- [ ] T009 [P] Layer 2 — implement `app/tenant_context.py` with `build_tenant_context(bearer: str) → dict`. Step 2: returns `{tenant_id, user_id}` constants from env vars (defaults `demo-tenant-001` / `demo-user-001`). Forward-compat docstring mentions Step 4 NextAuth replacement.

- [ ] T010 [P] Layer 2 — implement `app/forwarder.py` with module-level `httpx.AsyncClient` instance (with reasonable timeouts: 60s connect, 240s read for long uploads) and `forward_request(method, path, headers, body, files=None) → httpx.Response`. Routes the path against `LAYER3_BASE_URL`. Catches `httpx.RequestError` and re-raises as a typed `RenderEngineUnavailable` exception that the FastAPI exception handler turns into HTTP 503.

---

## Phase 3: User Story 1 — End-to-end render through Layer 2 → Layer 3 (P1) 🎯 MVP

**Story goal**: A solo founder submits a Mode 2 render via the wizard. Request hits Layer 2 (`:8080`) with a demo bearer; Layer 2 mints a JWT and forwards to Layer 3 (`:8090`); Layer 3 verifies and runs the render; the resulting MP4 is identical-quality to a Step 1 render but `script.json#params.tenant_id == "demo-tenant-001"`.

**Independent test**: Run all three services locally + submit a render via the wizard. Verify the network tab shows requests going to `:8080`, the resulting `script.json` has tenant_id, and the MP4 plays.

### Layer 2 — public routes (US1)

- [ ] T011 [P] [US1] Write LA-1..LA-3 tests in `visualai-orchestration/tests/contract/test_videos_forward.py`: missing/invalid bearer (401), valid bearer + JSON body forwards to a mock Layer 3 (assert URL, headers, body bytes).

- [ ] T012 [US1] Implement `app/routes/videos.py` with `POST /api/v1/videos`. Reads body as JSON, calls `verify_demo_bearer` then `mint_jwt` then `forward_request`. Returns Layer 3's response status + body verbatim.

- [ ] T013 [P] [US1] Write LA-4 test in `visualai-orchestration/tests/contract/test_tasks_forward.py`: GET /tasks/{id} forwards path param + query string + JWT.

- [ ] T014 [US1] Implement `app/routes/tasks.py` with `GET /api/v1/tasks/{task_id}`.

- [ ] T015 [P] [US1] Write LA-5 test in `visualai-orchestration/tests/contract/test_uploads_forward.py`: multipart bytes pass through; SHA-256 of forwarded body matches original; `role` form field forwarded.

- [ ] T016 [US1] Implement `app/routes/uploads.py` with `POST /api/v1/uploads/image` + `/audio`. Multipart proxying via `httpx.MultipartFormat` or streaming `request.stream()` + httpx `data=` + `files=`. Bearer + JWT mint same as videos route.

- [ ] T017 [P] [US1] Write LA-6 test in `visualai-orchestration/tests/contract/test_scripts_forward.py`: polish-preview JSON forwarded; 400 errors from Layer 3 propagate verbatim.

- [ ] T018 [US1] Implement `app/routes/scripts.py` with `POST /api/v1/scripts/polish-preview`.

- [ ] T019 [US1] Implement `app/main.py` (FastAPI app with `include_router` for each module + `/healthz` + `/readyz` + CORS middleware + global exception handler for `RenderEngineUnavailable` → 503). Wire `python main.py` to `uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("LAYER2_PORT", "8080")))`.

- [ ] T020 [US1] Run Layer 2's full test suite: `pytest visualai-orchestration/tests/ -q`. Verify LA-1..LA-10 + F2L3-1..F2L3-8 all pass (~18 tests total).

### Layer 3 — JWT middleware + schema (US1)

- [ ] T021 [P] [US1] Write JWT-1..JWT-9 tests in `MoneyPrinterTurbo/test/middleware/test_jwt_auth.py` (new file + `__init__.py` in `test/middleware/`). Cover: no header, non-Bearer scheme, malformed token, wrong key, expired, wrong issuer, wrong audience, missing tenant_id claim, valid bearer happy path. Use `pytest` fixtures to mint test JWTs with the test signing key.

- [ ] T022 [US1] Implement `app/middleware/__init__.py` + `app/middleware/jwt_auth.py` with `jwt_required(request)` and `jwt_required_with_body_injection(request)` per [contracts/layer3-jwt-middleware.md](contracts/layer3-jwt-middleware.md). Read `LAYER2_JWT_SIGNING_KEY` from env at module import time (cached). Honor `LAYER3_TRUST_LOCAL_UPSTREAM` fallback (FR-017) and synthetic-claims helper.

- [ ] T023 [P] [US1] Extend [app/models/schema.py](../../app/models/schema.py)'s `VideoParams` with `tenant_id: Optional[str]` + `user_id: Optional[str]` per [data-model.md §1](data-model.md#1-videoparams-extension-pydantic). Add `_validate_tenant_context` model_validator that enforces non-empty when `LAYER3_REQUIRE_TENANT_CONTEXT=true`.

- [ ] T024 [US1] Wire `Depends(jwt_required_with_body_injection)` on all routes in [app/controllers/v1/video.py](../../app/controllers/v1/video.py): `/videos`, `/subtitle`, `/audio` (the JSON-body create endpoints) and `Depends(jwt_required)` on the read endpoints (`/tasks`, `/tasks/{id}`).

- [ ] T025 [US1] Wire `Depends(jwt_required)` on [app/controllers/v1/uploads.py](../../app/controllers/v1/uploads.py)'s `/uploads/image` + `/uploads/audio` (multipart endpoints — body NOT injected).

- [ ] T026 [US1] Wire `Depends(jwt_required_with_body_injection)` on [app/controllers/v1/llm.py](../../app/controllers/v1/llm.py)'s `/scripts/polish-preview` and `Depends(jwt_required)` on `/scripts` + `/terms` (legacy upstream endpoints — required for Layer 2 forwarding to work).

- [ ] T027 [US1] Run Layer 3's JWT tests: `.venv/bin/pytest test/middleware/ -q`. Confirm JWT-1..JWT-17 all green.

- [ ] T028 [US1] Update existing Layer 3 test fixtures in [test/controllers/test_image_upload.py](../../test/controllers/test_image_upload.py) and [test/controllers/test_uploads_audio.py](../../test/controllers/test_uploads_audio.py) to add an `Authorization: Bearer <test_jwt>` header. Add a shared fixture `auth_header` in `test/controllers/conftest.py` that mints a test JWT with the test signing key. Run `.venv/bin/pytest test/controllers/ -q` — confirm green.

### Layer 1 — frontend retargeting (US1)

- [ ] T029 [P] [US1] Implement `visualai-frontend/src/lib/layer2-client.ts` per [contracts/frontend-layer2-wiring.md](contracts/frontend-layer2-wiring.md) §Helper extraction. Exports `layer2Url(path)`, `authHeaders()`, `layer2Fetch(path, init)`.

- [ ] T030 [P] [US1] Write FE-1..FE-3 Vitest tests in `visualai-frontend/tests/layer2-client.test.ts`: bearer attached from env, URL base correct, missing env handles gracefully.

- [ ] T031 [P] [US1] Update [visualai-frontend/src/app/api/generate/route.ts](../../../visualai-frontend/src/app/api/generate/route.ts): replace `MPT_BASE` reads with `layer2Fetch`; URL path stays `/api/v1/videos`. Verify the existing diagnostic console.log still surfaces what the wizard sent.

- [ ] T032 [P] [US1] Update [visualai-frontend/src/app/api/status/[taskId]/route.ts](../../../visualai-frontend/src/app/api/status/[taskId]/route.ts) to use `layer2Fetch`.

- [ ] T033 [P] [US1] Update [visualai-frontend/src/app/api/upload-image/route.ts](../../../visualai-frontend/src/app/api/upload-image/route.ts) to use `layer2Fetch` with multipart FormData.

- [ ] T034 [P] [US1] Update [visualai-frontend/src/app/api/upload-audio/route.ts](../../../visualai-frontend/src/app/api/upload-audio/route.ts) to use `layer2Fetch`.

- [ ] T035 [P] [US1] Update [visualai-frontend/src/app/api/polish-preview/route.ts](../../../visualai-frontend/src/app/api/polish-preview/route.ts) to use `layer2Fetch`.

- [ ] T036 [US1] Run frontend test suite: `cd visualai-frontend && pnpm vitest run`. Confirm 81+ tests still pass (existing 81 + ~3 new layer2-client tests).

### US1 verification

- [ ] T037 [US1] Manual end-to-end smoke test (quickstart Part 1): start Layer 2 + Layer 3 + frontend, submit a Mode 2 render via the wizard. Verify (a) Layer 2 logs show JWT mint, (b) Layer 3 logs show JWT verify with `tenant_id=demo-tenant-001`, (c) `script.json#params.tenant_id == "demo-tenant-001"`, (d) MP4 plays.

---

## Phase 4: User Story 2 — Tenant context in logs + audit (P1)

**Story goal**: Every Layer 3 log line emitted during a request carries `tenant_id` + `user_id` in the structured fields. The render worker thread inherits the context via VideoParams.

**Independent test**: Submit a render. Grep Layer 3's log file for the request_id; every line in that block contains `tenant_id="demo-tenant-001"`.

- [ ] T038 [P] [US2] Update Layer 3's loguru format string in [app/main.py](../../app/main.py) (or wherever the logger is configured) to include `{extra[tenant_id]}` + `{extra[user_id]}` with `-` defaults. Apply `logger.configure(extra={"tenant_id": "-", "user_id": "-"})` at startup so non-request log lines have safe defaults.

- [ ] T039 [P] [US2] In `app/middleware/jwt_auth.py`, wrap the request handler call in `with logger.contextualize(tenant_id=..., user_id=..., request_id=...)`. Verify by JWT-17 test that mock log captures contain the tenant fields.

- [ ] T040 [US2] In [app/services/task.py](../../app/services/task.py)'s `start()` function, add `with logger.contextualize(tenant_id=params.tenant_id, user_id=params.user_id, task_id=task_id):` wrapping the existing pipeline. This is a fourth touch line continuing debt #5 — but the touch is purely structural (a logger context), no new dispatch logic. Document in `STEP1_DEBT.md` row #5 as "Step-2 audit-context binding".

- [ ] T041 [US2] Manual smoke test (quickstart Part 3): two renders back-to-back; grep logs by request_id; verify tenant_id attached on every line.

---

## Phase 5: User Story 3 — Upstream MPT WebUI compat (P2)

**Story goal**: The upstream `webui/Main.py` continues to work locally when `LAYER3_TRUST_LOCAL_UPSTREAM=true`, regardless of Layer 2.

**Independent test**: Stop Layer 2. Set `LAYER3_TRUST_LOCAL_UPSTREAM=true` on Layer 3. `curl localhost:8090/api/v1/videos -d '...'` succeeds with synthetic upstream-demo tenant.

- [ ] T042 [P] [US3] Write JWT-13..JWT-15 tests in `test/middleware/test_jwt_auth.py`: trust-on + 127.0.0.1 + no header → accept; trust-on + 192.168.x + no header → reject; trust-off + 127.0.0.1 + no header → reject.

- [ ] T043 [US3] Implementation already present in T022 (`_trust_local_upstream` + `_synthetic_upstream_claims` helpers). Verify the JWT-13..15 tests pass.

- [ ] T044 [US3] Manual smoke test (quickstart Part 4): start ONLY Layer 3 with `LAYER3_TRUST_LOCAL_UPSTREAM=true`; curl directly; render runs with `tenant_id="upstream-demo"`.

---

## Phase 6: Polish & cross-cutting

- [ ] T045 Layer 3 — implement startup backfill `_maybe_backfill_uploads_to_tenant_layout()` per [research.md R5](research.md#r5--storage-path-migration). Hook into `app/main.py`'s `startup` event. Idempotent: skips files already in a tenant subdir.

- [ ] T046 Layer 3 — update `_require_under_uploads(path, tenant_id=None)` in [app/models/schema.py](../../app/models/schema.py) to accept the tenant_id param and validate against `storage/uploads/<tenant_id>/`. Pass tenant_id from the model_validator (which has access to `self.tenant_id`).

- [ ] T047 [P] Layer 3 — implement `_verify_production_safety()` in `app/main.py` startup hook (FR-018). JWT-16 test verifies the production-guard fires when expected.

- [ ] T048 [P] Layer 2 — mirror production-safety check in `visualai-orchestration/app/main.py` startup. LA-10 test verifies.

- [ ] T049 Update [STEP1_DEBT.md](../../STEP1_DEBT.md): strike through row #1 with `repaid in <Step-2 PR commit sha>` annotation; same for row #2; partially strike row #6 (Layer 3 Scope half repaid; storage location half remains for Step 3+).

- [ ] T050 Manual smoke tests (quickstart Parts 5–8): expired-JWT rejection, Layer 2 unreachable handling, storage backfill, production-guard refusal.

- [ ] T051 Open PR in `nexcognit-com/visualai-rendering-engine` with title `feat(014): orchestration layer + tenant plumbing — burn debts #1 + #2  NEX-XXX #in-review`. Body cites the constitution flip (Principle I + III: DEBT → PASS), test plan, debt strike-throughs.

- [ ] T052 Open PR in `nexcognit-com/visualai-orchestration` (NEW repo — first PR there) with the full Layer 2 service.

- [ ] T053 Push frontend changes to `nexcognit-com/visualai-frontend` main (no PR per existing pattern of bundled commits there).

---

## Dependencies

```text
Phase 1 (Setup)             → Phase 2 (Foundational)
Phase 2 (Foundational)      → Phase 3 (US1 — backend)
Phase 3 backend             → Phase 3 frontend
Phase 3 (US1) full          → Phase 4 (US2)  [US2 builds on US1's middleware]
Phase 3 (US1) full          → Phase 5 (US3)  [US3 toggles a flag in the same middleware]
Phases 3+4+5                → Phase 6 (Polish)
```

US2 and US5 can land in parallel after US1's middleware is wired; both touch the same `app/middleware/jwt_auth.py` file but only on additive lines (Loguru bind for US2, trust-flag fallback for US3 — the latter is already part of T022's implementation).

## Parallel-execution opportunities

Within Phase 2:
- T006 + T007 + T008 + T009 + T010 — five independent Layer 2 modules, no shared imports across them. Can be implemented in parallel.

Within Phase 3 backend:
- T011 + T013 + T015 + T017 — four contract tests in different files, all parallelizable.
- T012 + T014 + T016 + T018 — four route implementations after their respective tests, parallelizable.
- T021 (JWT tests) + T023 (schema extension) — parallel; different files.

Within Phase 3 frontend:
- T029 + T030 + T031–T035 — helper module + 5 proxy retargets — all parallelizable once the helper is written.

Within Phase 6:
- T047 + T048 — production-guards in two separate repos, parallel.

## Implementation strategy

**MVP scope = US1 only** (T001–T037, ~37 tasks, ~6 hours). The render-through-Layer-2 happy path is the entire deliverable for "Step 2 done". US2 (logs) and US3 (upstream compat) are additive on the same middleware; they can land in the same commit or as quick follow-ups.

**Recommended landing order**:
1. Phase 1 + Phase 2 (T001–T010): Layer 2 scaffold + foundational helpers — ~1 hour.
2. Phase 3 Layer 2 (T011–T020): Layer 2 routes + tests — ~1.5 hours.
3. Phase 3 Layer 3 (T021–T028): JWT middleware + schema + controller wiring + test fixture updates — ~2 hours.
4. Phase 3 Layer 1 (T029–T036): Frontend proxies + helper + tests — ~1 hour.
5. T037 manual smoke — 5 min.
6. Phases 4+5 (T038–T044): Loguru + upstream-trust — ~30 min (mostly already implemented in T022).
7. Phase 6 (T045–T053): polish, PR, debt strike-throughs — ~30 min.

Total: ~6–7 hours.

## Validation checklist

- [x] Every task has a checkbox + sequential ID + clear file path.
- [x] User-story tasks carry `[US1]`, `[US2]`, or `[US3]`; setup/foundational/polish tasks do not.
- [x] Parallel-safe tasks marked `[P]`.
- [x] Each user story has its own phase with an independent-test criterion.
- [x] Foundational tasks (T005–T010) gate every user-story phase.
- [x] Tests precede implementation within each story.
- [x] No task depends on a file the previous task hasn't touched.
