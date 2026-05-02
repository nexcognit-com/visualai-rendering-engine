# Research: Orchestration Layer + Tenant Plumbing (Step 2)

**Date**: 2026-05-03
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Five technical decisions blocked detailed planning. Each is resolved here so [data-model.md](data-model.md) and [contracts/](contracts/) can proceed without unknowns.

---

## R1 — JWT signing scheme: HMAC-SHA256 (HS256) for Step 2

**Decision**: Symmetric HMAC-SHA256 (HS256) with a single shared secret (`LAYER2_JWT_SIGNING_KEY`) configured into both Layer 2 and Layer 3 via env vars. The key value is generated at deploy time (`openssl rand -hex 32`) and stored in each service's untracked `.env` file.

**Rationale**:
- Step 2 has exactly two parties: Layer 2 (issuer) + Layer 3 (verifier). Both are services we control. Symmetric is structurally simpler than asymmetric for this case.
- HS256 is ~5× faster than RS256 for both mint and verify (matters at scale, not yet at Step 2's volume but worth getting right from the start).
- PyJWT supports HS256 natively in 5 lines: `jwt.encode(claims, secret, algorithm="HS256")` / `jwt.decode(token, secret, algorithms=["HS256"], audience=...)`.
- Key rotation is possible via `kid` (key ID) header support — we don't need it in Step 2 but the structure is documented in [contracts/layer3-jwt-middleware.md](contracts/layer3-jwt-middleware.md).
- Asymmetric (RS256) becomes the right choice when third parties need to verify Layer 2's tokens (e.g., NextAuth + cross-service trust in Step 4). Migration path: Layer 2 starts emitting RS256 with a `kid` header pointing at a JWKS endpoint; Layer 3 starts caching JWKS and verifying RS256 alongside HS256 during a transition window.

**Alternatives considered**:
- **RS256 from day 1**: rejected — needs key pair generation + public-key distribution machinery upfront for negligible Step 2 benefit; deferred to Step 4 alongside NextAuth.
- **No JWT, just shared bearer token**: rejected — bearer tokens carry no claims; we'd need a separate side-channel for tenant context, defeating the purpose. JWT puts tenant_id + user_id IN the token, signed.
- **Static API keys per service-pair**: rejected — same problem as bearer; no claims structure.

**Spec impact**: FR-004 (HS256), FR-008 (Layer 3 verify with same key) are honored as written.

---

## R2 — Loguru tenant context propagation across thread boundaries

**Decision**: Use Loguru's `logger.contextualize(...)` context manager + `loguru._defaults.LOGURU_CONTEXT_VAR` (Loguru exposes `loguru.logger.bind()` for additive context). The JWT middleware enters a context-vars block at request entry; Loguru's default formatter picks up `tenant_id` + `user_id` automatically via the `{extra[tenant_id]}` placeholder in the format string.

For the **render worker thread** (Layer 3 dispatches renders to a background thread via `task_manager.add_task`), context vars don't propagate by default. Two viable patterns:

1. **Capture + replay**: middleware captures `(tenant_id, user_id)` into a dict; the dispatcher passes it explicitly to the worker; the worker enters a fresh `logger.contextualize(...)` at task start.
2. **Snapshot via contextvars**: the dispatcher uses `contextvars.copy_context().run(worker_fn)` to copy the context vars across the thread boundary.

**Decision: Pattern 1 (explicit capture + replay)**. Rationale: simpler, more debuggable, works regardless of whether the thread pool uses asyncio or threading. The worker function gains a `tenant_context: dict` parameter and binds it before any other logger calls.

**Implementation sketch**:

```python
# In app/middleware/jwt_auth.py — at request entry:
from loguru import logger
async def jwt_dependency(request: Request) -> dict:
    claims = verify_jwt(...)
    request.state.tenant_id = claims["tenant_id"]
    request.state.user_id = claims["user_id"]
    request.state.request_id = claims["jti"]
    return claims  # FastAPI injects into route handlers via Depends(jwt_dependency)

# In app/controllers/v1/video.py — at task dispatch:
def create_task(request, body, stop_at):
    tenant_ctx = {
        "tenant_id": request.state.tenant_id,
        "user_id": request.state.user_id,
        "request_id": request.state.request_id,
    }
    task_manager.add_task(tm.start, task_id=task_id, params=body, stop_at=stop_at,
                          tenant_context=tenant_ctx)

# In app/services/task.py:start (NOT modified — instead, pass tenant_ctx via params):
# Actually: extend VideoParams with tenant_context fields so it flows naturally
# without a new arg to task.start. See data-model.md §1.

# Then inside the worker: logger.contextualize(**tenant_ctx) wraps the entire pipeline.
```

**Alternatives considered**:
- **`contextvars.copy_context().run(...)`**: rejected — Layer 3's `task_manager` uses raw threading (memory or Redis); copy_context only works with asyncio/Trio out of the box. Wrapping it would add a runtime adapter we don't need.
- **Embedding tenant context inside the params dict and binding in the worker**: this IS the pattern we're using (since `VideoParams` already gets the tenant fields per FR-011). The capture-replay sketch above is technically just "VideoParams.tenant_id flows into the worker via the existing params arg".

**Spec impact**: FR-012 honored. The implementation extends `VideoParams` with tenant fields (FR-011 already mandates this) and the worker reads them at task start.

---

## R3 — Layer 2 framework: FastAPI + httpx forwarder

**Decision**: FastAPI for routing (matches Layer 3's stack, same Python runtime) + httpx for the upstream HTTP forwarder. Async throughout. Multipart proxying via `python-multipart` (already a FastAPI transitive dep) plus `httpx.MultipartFormat` for the upload endpoints.

**Rationale**:
- FastAPI is the constitution-aligned default for Python services in this stack. Same patterns as Layer 3 (router registration, dependency injection, Pydantic models).
- httpx async client allows non-blocking forwarding; even at single-user scale this matters because uploads can be 10 MB and we don't want to block the event loop.
- Multipart pass-through is well-supported — httpx accepts a `files=` dict keyed by field name with `(filename, content, content_type)` tuples; stream-based forwarding is supported but Step 2's volume doesn't need it.
- The FastAPI `@app.post(...)` decorator + dependency-injection-based bearer validation is ~20 lines per endpoint.

**Layer 2 file shape** (per [plan.md](plan.md) §Project Structure):

```text
visualai-orchestration/app/
├── main.py            # FastAPI() instance + uvicorn.run(); include_router(...) for each module
├── config.py          # pydantic-settings or os.getenv() for LAYER3_BASE_URL, LAYER2_DEMO_BEARER, LAYER2_JWT_SIGNING_KEY
├── auth/
│   ├── bearer.py      # FastAPI Depends function: verify Authorization: Bearer <demo>
│   └── jwt_issuer.py  # mint_jwt(tenant_id, user_id) → str
├── routes/*.py        # one module per Layer 3 endpoint group
├── forwarder.py       # singleton httpx.AsyncClient + forward_request(method, path, body, headers, files?)
└── tenant_context.py  # build_tenant_context() → dict (Step 2: returns demo constants)
```

**Alternatives considered**:
- **Cloudflare Workers / Deno / Edge runtime**: rejected — different runtime than Layer 3 means duplicated tooling (TypeScript or JS), different deployment, different testing infrastructure. Step 2 isn't the right time to introduce that diversity. Edge becomes worth considering in Step 5 when latency-sensitive scaling matters.
- **Express / Node**: rejected — same reason; introduces a second runtime in the stack.
- **Caddy / Nginx with Lua scripting**: rejected — too low-level for the JWT-mint logic; would push business logic into config files.

**Spec impact**: FR-001 (FastAPI service). No spec edit needed.

---

## R4 — Frontend bearer storage: `NEXT_PUBLIC_*` vs server-side

**Decision**: Use `NEXT_PUBLIC_LAYER2_DEMO_BEARER` (browser-exposed) for Step 2. Replace with NextAuth-issued, server-side-rotated tokens in Step 4.

**Rationale**:
- The demo bearer is NOT a real secret — anyone running the local stack has access to the same value via `cp .env.example .env`. Hardening it for Step 2 would be performative security.
- `NEXT_PUBLIC_*` exposure pattern matches how `NEXT_PUBLIC_LAYER3_URL` is already used in Step 1's wizard. Consistent.
- Server-side credential issuance requires NextAuth (Step 4) — premature in Step 2.
- Production-guard (FR-018) catches the case where a deployed environment forgets to swap the demo bearer for a real credential.

**Migration path to Step 4**: replace `NEXT_PUBLIC_LAYER2_DEMO_BEARER` with a NextAuth callback that exchanges the user's session for a Layer 2 JWT via `POST /api/v1/auth/exchange`. The wizard's proxy routes (`/api/generate`, etc.) read the JWT from the session via `getServerSession()` and forward it. The `NEXT_PUBLIC_*` var becomes obsolete.

**Alternatives considered**:
- **Session-based auth from day 1 (no token in browser)**: rejected — requires NextAuth plumbing that's a Step 4 deliverable. Step 2 is single-user demo; this would be wasted work.
- **OIDC / OAuth2 from day 1**: rejected — same reason; massive overshoot for "single-user demo".
- **`.env.local` (server-only)**: rejected — Next.js's `NEXT_PUBLIC_*` is the documented pattern for browser-accessible config; separating server-only vars adds unnecessary indirection at this scale.

**Spec impact**: FR-015 (NEXT_PUBLIC_* is acceptable for demo). No spec edit needed.

---

## R5 — Storage path migration: `storage/uploads/<tenant_id>/<uuid>.<ext>`

**Decision**: At Step 2 deploy time, run a one-time backfill that moves any existing `storage/uploads/<uuid>.<ext>` files into `storage/uploads/demo-tenant-001/<uuid>.<ext>`. The backfill is idempotent (skips files already in a tenant subdir). After the backfill, all new uploads go directly to the tenant-prefixed path.

**Rationale**:
- FR-020 mandates the path migration. Step 1's flat layout was a debt.
- Existing demo content from Step 1 testing should still be accessible — no point breaking the My Assets page UX for the founder.
- Backfill is trivial in Python (one `for f in os.listdir(uploads_dir): if not in tenant subdir: shutil.move(...)` loop). ~15 lines including the idempotency check.
- The path-traversal guard `_require_under_uploads` (in `schema.py`) already validates against `storage/uploads/`; updating it to require an additional segment under uploads is one line change.

**Implementation site**:

```python
# app/middleware/jwt_auth.py — backfill runs once at app startup, NOT per-request:
def _maybe_backfill_uploads_to_tenant_layout():
    """Idempotent migration: storage/uploads/<uuid>.<ext> → storage/uploads/demo-tenant-001/<uuid>.<ext>"""
    uploads_dir = utils.storage_dir("uploads", create=True)
    legacy_files = [f for f in os.listdir(uploads_dir)
                    if os.path.isfile(os.path.join(uploads_dir, f))]
    if not legacy_files:
        return
    target_dir = os.path.join(uploads_dir, "demo-tenant-001")
    os.makedirs(target_dir, exist_ok=True)
    for f in legacy_files:
        src = os.path.join(uploads_dir, f)
        dst = os.path.join(target_dir, f)
        if not os.path.exists(dst):
            shutil.move(src, dst)
    logger.info(f"backfilled {len(legacy_files)} legacy uploads to demo-tenant-001/")

# Wire into FastAPI startup:
@app.on_event("startup")
async def startup():
    _maybe_backfill_uploads_to_tenant_layout()
```

**Alternatives considered**:
- **Don't backfill — leave orphans**: rejected — breaks the My Assets page for already-uploaded demo content.
- **Backfill on-demand at first read**: rejected — too magical, harder to debug.
- **Symlink legacy paths into the tenant subdir**: rejected — symlink handling on Windows / cross-platform is fragile; explicit move is simpler.

**Spec impact**: FR-020 honored. The backfill is implementation detail; spec doesn't need edits.

---

## Decisions consolidated

| ID | Decision | Spec impact | Files affected |
|---|---|---|---|
| R1 | HS256 JWT with shared secret; key rotation deferred to Step 4 | None | Layer 2 `app/auth/jwt_issuer.py`; Layer 3 `app/middleware/jwt_auth.py` |
| R2 | Loguru `contextualize()` at middleware + capture-replay across threads | None | Layer 3 `app/middleware/jwt_auth.py` + `app/services/task.py` (passive — reads VideoParams.tenant_id) |
| R3 | FastAPI + httpx for Layer 2 forwarder | None | Layer 2 service architecture |
| R4 | `NEXT_PUBLIC_LAYER2_DEMO_BEARER` for Step 2; Step 4 swaps to NextAuth | None | Layer 1 `.env.example` + proxy route handlers |
| R5 | One-time backfill of `storage/uploads/` at Layer 3 startup | None | Layer 3 `app/middleware/jwt_auth.py` (startup hook) + `app/models/schema.py` (path-guard update) |

All five `NEEDS CLARIFICATION` candidates resolved with rationale documented. Phase 1 design unblocked.
