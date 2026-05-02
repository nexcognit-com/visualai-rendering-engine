# Quickstart: Orchestration Layer + Tenant Plumbing (Step 2)

**Feature**: 014-orchestration-tenant
**Goal**: Manually verify Layer 1 → Layer 2 → Layer 3 round-trip + tenant context propagation before declaring Step 2 implemented.

## Prerequisites

1. Layer 3 (this repo) running on `:8090` with new JWT middleware: `python main.py` from `MoneyPrinterTurbo/`.
2. Layer 2 running on `:8080` (new sibling repo): `python main.py` from `../visualai-orchestration/`.
3. Layer 1 (`../visualai-frontend/`) running on `:3001`: `pnpm dev`.
4. Both Layer 2 and Layer 3 share the same `LAYER2_JWT_SIGNING_KEY` env var value.
5. Layer 1 has `NEXT_PUBLIC_LAYER2_URL=http://localhost:8080` and `NEXT_PUBLIC_LAYER2_DEMO_BEARER=<bearer>` matching Layer 2's `LAYER2_DEMO_BEARER`.

## Part 1 — Tenant context end-to-end (US1)

1. Open `http://localhost:3001/modes/short-video` in a browser.
2. Pick **Auto** for visuals + **Auto** for script. Type a subject like "morning yoga routine".
3. Click Generate.
4. **Expected**: Network tab shows `POST http://localhost:8080/api/generate` with `Authorization: Bearer <demo>` header. Layer 2 logs show "minted JWT for tenant_id=demo-tenant-001". Layer 3 logs show "verified JWT, tenant_id=demo-tenant-001, user_id=demo-user-001".
5. After render completes, check `storage/tasks/<task_id>/script.json` — `params.tenant_id` should be `"demo-tenant-001"` and `params.user_id` should be `"demo-user-001"`.

**Pass criteria**: SC-001 (audit log has tenant_id), SC-005 (logs are tenant-tagged).

## Part 2 — Direct Layer 3 calls rejected (US1 / SC-002)

1. With Layer 3 running and `LAYER3_TRUST_LOCAL_UPSTREAM=false` (production setting):
2. Run:
   ```sh
   curl -i -X POST http://localhost:8090/api/v1/videos \
     -H "Content-Type: application/json" \
     -d '{"video_subject":"unauthorized","video_aspect":"9:16","voice_name":"en-US-JennyNeural-Female","video_count":1,"paragraph_number":1}'
   ```
3. **Expected**: HTTP 401 with body `{"detail":{"error_code":"missing_jwt", ...}}`.

**Pass criteria**: SC-002 (direct calls rejected 100%).

## Part 3 — Tenant log isolation (US2)

1. With Layer 2 + Layer 3 + Layer 1 all running, submit two renders back-to-back from the wizard. (Both will land as `demo-tenant-001` in Step 2 — the test verifies LOG ISOLATION, not multi-tenant data isolation, which is Step 4.)
2. Tail Layer 3's stdout: `tail -f /tmp/mpt.log` (or wherever loguru writes).
3. **Expected**: Every log line includes `tenant_id=demo-tenant-001` and `user_id=demo-user-001` in the structured fields.
4. Grep: `grep "tenant_id=demo-tenant-001" /tmp/mpt.log | wc -l` should match the total Layer-3 log count for those two requests (no orphan log lines without tenant context).

**Pass criteria**: SC-005.

## Part 4 — Synthetic multi-tenant test

1. Stop Layer 2.
2. Set `LAYER3_TRUST_LOCAL_UPSTREAM=true` on Layer 3 (already false in production).
3. Run the upstream MPT WebUI (`python -m streamlit run webui/Main.py`) or curl directly:
   ```sh
   curl -X POST http://localhost:8090/api/v1/videos \
     -H "Content-Type: application/json" \
     -d '{"video_subject":"upstream-test","video_aspect":"9:16","voice_name":"en-US-JennyNeural-Female","video_count":1,"paragraph_number":1}'
   ```
4. **Expected**: HTTP 200 with task_id. Render proceeds. `script.json#params.tenant_id == "upstream-demo"`.

**Pass criteria**: US3 / SC-007 (upstream WebUI compat).

## Part 5 — JWT expired handling

1. Generate a JWT with `exp` 5 minutes in the past:
   ```sh
   python -c "
   import jwt, time
   token = jwt.encode({
     'iss': 'visualai-orchestration', 'aud': 'visualai-rendering-engine',
     'tenant_id': 'demo-tenant-001', 'user_id': 'demo-user-001',
     'iat': int(time.time()) - 3600, 'exp': int(time.time()) - 300, 'jti': 'expired-test'
   }, '<your LAYER2_JWT_SIGNING_KEY>', algorithm='HS256')
   print(token)
   "
   ```
2. Hit Layer 3 with this token:
   ```sh
   curl -i -X POST http://localhost:8090/api/v1/videos \
     -H "Authorization: Bearer <expired_token>" \
     -H "Content-Type: application/json" \
     -d '{...}'
   ```
3. **Expected**: HTTP 401 with `error_code: "expired_jwt"`.

**Pass criteria**: JWT validation per [layer3-jwt-middleware.md](contracts/layer3-jwt-middleware.md).

## Part 6 — Layer 2 unreachable

1. With Layer 2 stopped, hit Layer 1's `/api/generate` from the wizard.
2. **Expected**: Wizard surfaces "orchestration service unavailable" toast (HTTP 503 from the proxy, error_code `layer2_unavailable`).
3. The wizard does NOT fall back to a direct `localhost:8090` call.

**Pass criteria**: FR-016, SC-002.

## Part 7 — Storage path migration (FR-020)

1. Pre-Step-2 state: a few `storage/uploads/<uuid>.<ext>` files in the flat layout.
2. Restart Layer 3.
3. **Expected**: `storage/uploads/demo-tenant-001/` directory created; legacy files moved into it. Idempotent on re-run.

**Pass criteria**: FR-020. Verified by `ls storage/uploads/demo-tenant-001/` showing the legacy files.

## Part 8 — Production guard (FR-018)

1. Set `LAYER3_ENV=production` AND `LAYER3_TRUST_LOCAL_UPSTREAM=true` AND start Layer 3.
2. **Expected**: Layer 3 fails to start with `RuntimeError: PRODUCTION SAFETY: LAYER3_TRUST_LOCAL_UPSTREAM=true is forbidden in production`.
3. Same test on Layer 2 with `LAYER2_ENV=production` + default-placeholder `LAYER2_JWT_SIGNING_KEY` → Layer 2 fails to start.

**Pass criteria**: FR-018.

## Sign-off

Step 2 is implementation-complete when:

- [ ] Parts 1–8 pass.
- [ ] STEP1_DEBT.md row #1 + #2 are struck through with this PR's commit sha.
- [ ] Constitution check section in the PR description shows Principle I + III flipped from DEBT to PASS.
- [ ] All Layer 3 backend tests pass with the JWT-bearing fixture (existing 76 tests gain `Authorization: Bearer ...` headers).
- [ ] Layer 2 backend tests (LA-1..LA-10, F2L3-1..F2L3-8) all green.
- [ ] Frontend tests (FE-1..FE-7) all green.
- [ ] Manual end-to-end render through Layer 1 → Layer 2 → Layer 3 produces a 9:16 MP4 in ≤ 92s (Step 1 baseline + ≤ 2s overhead per SC-003).
