# Contract: Layer 2 → Layer 3 Forwarding

**Feature**: 014-orchestration-tenant
**Layer**: Orchestration (Layer 2) → Rendering (Layer 3)

Defines the wire shape Layer 2 emits when forwarding a request to Layer 3, and the JWT structure Layer 3 verifies.

---

## Forwarding shape

For every authenticated incoming request, Layer 2:

1. Validates the demo bearer (per [layer2-api.md](layer2-api.md)).
2. Calls `tenant_context.build_tenant_context(bearer)` → returns `{tenant_id, user_id}` (Step 2: demo constants).
3. Mints a JWT via `auth/jwt_issuer.py:mint_jwt(tenant_id, user_id)` → returns a signed token string + `jti` request_id.
4. Forwards the request to Layer 3 with:
   - Same HTTP method.
   - Same path: `{LAYER3_BASE_URL}{request.url.path}{?query_string}`.
   - **Replaces** the `Authorization` header: `Bearer <minted_jwt>` (the original demo bearer is dropped).
   - Adds `X-Request-ID: <jti>` for cross-tier log correlation.
   - Body forwarded verbatim (JSON or multipart).
5. Returns Layer 3's response body and status code verbatim, with one exception: if the upstream call raises (timeout, connection refused), Layer 2 returns:

```json
{ "error_code": "render_engine_unavailable", "detail": "..." }
```

with HTTP 503.

---

## JWT structure (HS256)

Header:
```json
{ "alg": "HS256", "typ": "JWT" }
```

Claims:
```json
{
  "iss": "visualai-orchestration",
  "aud": "visualai-rendering-engine",
  "sub": "demo-user-001",
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "iat": 1714867200,
  "exp": 1714868100,
  "jti": "01HSNPQ8K5J9X3M7Z2T6F4WAYV"
}
```

- `iss` and `aud` are constants per [data-model.md §2](../data-model.md#2-jwt-claims).
- `sub`, `tenant_id`, `user_id` come from `build_tenant_context()` output. Step 2: all hardcoded constants.
- `iat`: `int(time.time())`.
- `exp`: `iat + 900` (15 minutes).
- `jti`: 26-char ULID. Generated via `python-ulid` lib (or `secrets.token_urlsafe(20)` if we don't want a new dep).

Signing: `jwt.encode(claims, LAYER2_JWT_SIGNING_KEY, algorithm="HS256")`.

---

## Layer 3 verification semantics

Layer 3 checks (in this order):
1. `Authorization: Bearer <token>` header present → else 401 `missing_jwt`.
2. Token decodes → else 401 `invalid_jwt`.
3. `iss == "visualai-orchestration"` → else 401 `invalid_jwt`.
4. `aud == "visualai-rendering-engine"` → else 401 `invalid_jwt`.
5. `exp > now() - 30s` (30s clock skew) → else 401 `expired_jwt`.
6. `tenant_id` non-empty string → else 401 `invalid_jwt`.
7. `user_id` non-empty string → else 401 `invalid_jwt`.

PyJWT one-liner that handles 1-5 atomically:

```python
claims = jwt.decode(
    token,
    LAYER2_JWT_SIGNING_KEY,
    algorithms=["HS256"],
    audience="visualai-rendering-engine",
    issuer="visualai-orchestration",
    leeway=30,
)
```

Steps 6-7 are explicit checks after decode succeeds.

---

## Tenant context injection

After verification, Layer 3's middleware (`app/middleware/jwt_auth.py`) MUST:

1. Set `request.state.tenant_id`, `request.state.user_id`, `request.state.request_id` (= `jti`), `request.state.jwt_claims`.
2. **Inject `tenant_id` and `user_id` into the request body** before Pydantic parsing for endpoints that accept a JSON body (POST /videos, POST /scripts/polish-preview). The injection is implemented by reading the body, parsing as JSON, merging the claims, re-serializing, and replacing the request body stream. (See [layer3-jwt-middleware.md](layer3-jwt-middleware.md) for the implementation pattern.)
3. For multipart endpoints (POST /uploads/image, /audio): no body injection — those endpoints don't carry tenant_id in the body. The middleware just sets `request.state` for the controller to read.
4. For GET /tasks/{task_id}: same — no body, just request.state.
5. Enter a Loguru contextualize block: `logger.contextualize(tenant_id=..., user_id=..., request_id=...)`.

---

## Test coverage (planned)

| Test | Description |
|---|---|
| F2L3-1 | Layer 2 mints valid JWT; Layer 3 mock controller receives Authorization: Bearer with HS256 signature. |
| F2L3-2 | JWT contains tenant_id="demo-tenant-001" + user_id="demo-user-001" (Step 2 constants). |
| F2L3-3 | jti is a fresh ULID per request (no two requests share a jti). |
| F2L3-4 | exp is iat + 900 seconds. |
| F2L3-5 | X-Request-ID header is set to the same value as jti. |
| F2L3-6 | Original demo bearer NOT forwarded — Layer 3 only sees the JWT. |
| F2L3-7 | Multipart bytes pass through unchanged (sha256 of forwarded body == original body). |
| F2L3-8 | If Layer 3 returns 401 invalid_jwt (e.g., wrong key), Layer 2 propagates verbatim. |
