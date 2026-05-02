# Data Model: Orchestration Layer + Tenant Plumbing (Step 2)

**Date**: 2026-05-03
**Spec**: [spec.md](spec.md) — Key Entities §
**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Step 2 introduces no database. All "data" lives in transient request state, JWT claims, and (post-render) the existing `script.json` audit file. This document defines the shapes and validation rules.

---

## 1. `VideoParams` extension (Pydantic)

Two new required fields are added to `app/models/schema.py`'s `VideoParams` class:

```python
# app/models/schema.py — additions only

class VideoParams(BaseModel):
    # ... existing fields preserved unchanged ...

    # Spec 014: tenant context. Required when LAYER3_REQUIRE_TENANT_CONTEXT=true
    # (production default after Step 2). Falsy values acceptable in development
    # mode for the Step 1 transition window — the JWT middleware injects these
    # from claims before Pydantic parsing, so the controller's body never sees
    # missing values in production.
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_tenant_context(self) -> "VideoParams":
        # When the production flag is set, both fields must be non-empty.
        # The JWT middleware always populates them from claims, so a missing
        # value here means either:
        #   - the request bypassed the middleware (impossible in production),
        #   - or the JWT lacked the claims (will have already been rejected).
        # This is a defense-in-depth check.
        if not _require_tenant_context():
            return self
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError("tenant_id_required")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id_required")
        return self


def _require_tenant_context() -> bool:
    """Read at validate-time so tests can monkey-patch without restart."""
    return os.environ.get("LAYER3_REQUIRE_TENANT_CONTEXT", "false").lower() in ("true", "1", "yes")
```

### Validation rules

| Field | Type | Required when | Notes |
|---|---|---|---|
| `tenant_id` | `Optional[str]` (becomes required at runtime) | `LAYER3_REQUIRE_TENANT_CONTEXT=true` | Non-empty string. Source: JWT `tenant_id` claim, copied into request body by middleware before Pydantic parsing. |
| `user_id` | `Optional[str]` (becomes required at runtime) | same | Same source pattern. |

Both fields are `Optional[str]` at the Pydantic schema level so the Step 1 transition window (with `LAYER3_REQUIRE_TENANT_CONTEXT=false`) doesn't break legacy callers. Production runtime flips the flag to `true`, at which point the validator enforces non-empty.

### Backward compatibility

- Step 1 callers with no JWT and no tenant context → `LAYER3_REQUIRE_TENANT_CONTEXT=false` (dev) or rejected by middleware (prod, with `LAYER3_TRUST_LOCAL_UPSTREAM=false`).
- Step 1 dev path (`LAYER3_TRUST_LOCAL_UPSTREAM=true` + no JWT + 127.0.0.1): middleware injects synthetic `tenant_id="upstream-demo"`, `user_id="upstream-demo-user"`; validator passes.

---

## 2. JWT Claims

The token shape minted by Layer 2 and verified by Layer 3.

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

### Field semantics

| Claim | Type | Notes |
|---|---|---|
| `iss` | string (constant) | `"visualai-orchestration"` — issuer; Layer 3 verifies. |
| `aud` | string (constant) | `"visualai-rendering-engine"` — audience; Layer 3 verifies. |
| `sub` | string | Subject (RFC 7519). Mirrors `user_id` for Step 2; in Step 4 with NextAuth this becomes the canonical user identifier. |
| `tenant_id` | string | Custom claim — owning tenant. Step 2: constant `"demo-tenant-001"`. |
| `user_id` | string | Custom claim — the acting user within the tenant. Step 2: constant `"demo-user-001"`. |
| `iat` | int (Unix epoch) | Issued-at timestamp. |
| `exp` | int (Unix epoch) | Expiration. **15 minutes** from `iat` per FR-004. |
| `jti` | string | Unique token ID — used as `request_id` for log correlation across Layer 2 / Layer 3. ULID format (sortable, ~26 chars). |

### Algorithm + signature

- Algorithm: `HS256` (HMAC-SHA256). Specified in the JWT header.
- Signing key: `LAYER2_JWT_SIGNING_KEY` env var, generated via `openssl rand -hex 32` (256 bits).
- Both Layer 2 and Layer 3 read the same key from their respective `.env` files.

### Validation (Layer 3 side)

Layer 3 MUST verify:
1. Signature matches HS256 over the header + payload using `LAYER2_JWT_SIGNING_KEY`.
2. `iss == "visualai-orchestration"`.
3. `aud == "visualai-rendering-engine"`.
4. `exp > now()` (with 30-second clock skew tolerance).
5. `tenant_id` and `user_id` claims are present and non-empty strings.

Failures map to:
- Bad signature / malformed → `error_code: "invalid_jwt"`, HTTP 401.
- Expired (`exp <= now()`) → `error_code: "expired_jwt"`, HTTP 401.
- Missing claims → `error_code: "invalid_jwt"`, HTTP 401.
- No `Authorization: Bearer ...` header → `error_code: "missing_jwt"`, HTTP 401 (unless `LAYER3_TRUST_LOCAL_UPSTREAM=true` AND request is from `127.0.0.1`).

---

## 3. Tenant Context (Layer 3 internal)

The Layer-3-internal binding between a request and its owning tenant for the duration of the render. Lives in `request.state` (FastAPI's per-request scratchpad) and is bound into Loguru's context via `logger.contextualize(...)`.

```python
# Set by app/middleware/jwt_auth.py at request entry:
request.state.tenant_id: str         # from JWT claim
request.state.user_id: str           # from JWT claim
request.state.request_id: str        # from JWT jti claim — same value Layer 2 minted
request.state.jwt_claims: dict       # full claim dict for audit purposes
```

The render worker thread reads these from `VideoParams.tenant_id` + `user_id` (which were merged into the body by the middleware) and re-binds Loguru at task start.

### Loguru contextualization

```python
# app/middleware/jwt_auth.py — at request entry:
with logger.contextualize(tenant_id=tenant_id, user_id=user_id, request_id=request_id):
    response = await call_next(request)

# app/services/task.py — at task worker entry (already inside a thread):
with logger.contextualize(tenant_id=params.tenant_id, user_id=params.user_id, task_id=task_id):
    # ... existing render pipeline ...
```

The Loguru format string is updated to include `extra[tenant_id]` etc., e.g.:

```python
# In logging config:
"<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
"<cyan>tenant={extra[tenant_id]}</cyan> | <cyan>user={extra[user_id]}</cyan> | "
"<level>{message}</level>"
```

Lines emitted outside a contextualize block (e.g., startup logs) get `tenant_id="-"` / `user_id="-"` defaults via Loguru's `patcher`.

---

## 4. `script.json` audit log extension

Existing `storage/tasks/<task_id>/script.json` gains tenant fields in its `params` block (since `params` is `body.model_dump()`):

```json
{
  "params": {
    "video_subject": "...",
    "video_script": "...",
    "tenant_id": "demo-tenant-001",
    "user_id": "demo-user-001",
    ...
  },
  "script": "...",
  "search_terms": [...],
  "asset_audit": { ... }  // existing spec 006 audit unchanged
}
```

No schema-version bump needed — `params` is a flat dict serialized from `VideoParams.model_dump()`; new fields appear automatically.

---

## 5. Storage path migration

```text
Before (Step 1):                     After (Step 2):
storage/uploads/                      storage/uploads/
└── <uuid>.<ext>                      └── <tenant_id>/
                                          └── <uuid>.<ext>
```

The `_require_under_uploads` validator in `schema.py` is updated:

```python
def _require_under_uploads(path: str, tenant_id: Optional[str] = None) -> None:
    """Reject paths that don't resolve under storage/uploads/<tenant_id>/."""
    uploads_dir = os.path.realpath(os.path.join(os.getcwd(), "storage", "uploads"))
    if tenant_id:
        # Step 2: tenant-scoped layout
        target_dir = os.path.realpath(os.path.join(uploads_dir, tenant_id))
    else:
        # Step 1 transition fallback: any subdir under uploads/ ok
        target_dir = uploads_dir
    real = os.path.realpath(path) if os.path.isabs(path) else os.path.realpath(
        os.path.join(os.getcwd(), path)
    )
    if not real.startswith(target_dir + os.sep) and real != target_dir:
        raise ValueError("path_outside_uploads")
```

When `LAYER3_REQUIRE_TENANT_CONTEXT=true`, the model_validator passes `self.tenant_id` to the path-traversal guard. Otherwise it falls back to the looser Step-1 check.

### Backfill (one-time at startup)

Per [research.md R5](research.md#r5--storage-path-migration), a startup hook moves legacy `storage/uploads/<uuid>.<ext>` into `storage/uploads/demo-tenant-001/<uuid>.<ext>` once.

---

## 6. Layer 2 internal state (none persistent)

Layer 2 is **stateless**. No DB, no filesystem state, no cache (Step 2 doesn't need rate-limiting or token revocation lists yet).

### Per-request transient state (in-memory only)

```python
# Inside a Layer 2 request handler:
class ForwardingContext:
    bearer_token: str         # validated demo bearer
    tenant_id: str            # constant "demo-tenant-001" in Step 2
    user_id: str              # constant "demo-user-001"
    minted_jwt: str           # the JWT sent to Layer 3
    request_id: str           # JWT jti — same value used in Layer 3 logs
    upstream_url: str         # full Layer 3 URL: f"{LAYER3_BASE_URL}{request.path}"
```

Discarded after the response is sent. Future steps may add request-correlation tracing (OpenTelemetry) but Step 2 is just `loguru` log lines on both sides keyed by `request_id`.

---

## 7. Demo Tenant (constants)

```python
# Layer 2 — visualai-orchestration/app/tenant_context.py
DEMO_TENANT = {
    "tenant_id": os.environ.get("LAYER2_DEMO_TENANT_ID", "demo-tenant-001"),
    "user_id": os.environ.get("LAYER2_DEMO_USER_ID", "demo-user-001"),
}

def build_tenant_context(bearer: str) -> dict:
    """Step 2: returns the demo tenant for any valid bearer.
    Step 4: looks up the actual tenant from the user's NextAuth session."""
    return DEMO_TENANT.copy()
```

### Future migration to real tenants (Step 4)

`build_tenant_context()` becomes a real lookup against the NextAuth + Wix CRM data layer. The function signature stays the same, so JWT-mint code doesn't change — it just gets a real tenant_id back instead of the demo constant.

---

## 8. Frontend wizard state — no schema changes

The Step 2 wizard adds NO new state beyond:
- `process.env.NEXT_PUBLIC_LAYER2_URL` (replaces `LAYER3_URL`).
- `process.env.NEXT_PUBLIC_LAYER2_DEMO_BEARER` (new — sent in Authorization header).

All proxy routes (`/api/generate`, `/api/status/[taskId]`, `/api/upload-image`, `/api/upload-audio`, `/api/polish-preview`) read the bearer at request-time and attach it to the upstream `fetch(LAYER2_URL, { headers: { Authorization: \`Bearer ${bearer}\` } })`. No wizard-state changes; the change is purely in the proxy plumbing.
