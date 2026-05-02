# Contract: Layer 3 JWT Middleware

**Feature**: 014-orchestration-tenant
**Layer**: Rendering (Layer 3, this repo)
**File**: `app/middleware/jwt_auth.py` (new)

Defines the JWT verification + tenant-context-injection middleware applied to Layer 3's video controllers. Mounted as a FastAPI **dependency** (not a global ASGI middleware) so the upstream MoneyPrinterTurbo controllers we don't protect (e.g., legacy `/api/process` if any exist on the upstream side) stay unaffected.

---

## Wiring shape

The middleware exposes two callables:

```python
# app/middleware/jwt_auth.py

def jwt_required(request: Request) -> dict:
    """FastAPI dependency: verifies Authorization header, sets request.state,
    enters Loguru contextualize, returns the claims dict.

    Raises HTTPException with status_code=401 + typed error_code on failure.
    """

async def jwt_required_with_body_injection(request: Request) -> dict:
    """Variant for JSON-body endpoints (POST /videos, POST /scripts/polish-preview).

    Reads the request body, merges tenant_id + user_id into the JSON, replaces
    the body stream so downstream Pydantic parsing sees the augmented body.
    Returns the claims dict same as jwt_required.
    """
```

Each Layer 3 controller wires the appropriate variant via `Depends`:

```python
# app/controllers/v1/video.py
from app.middleware.jwt_auth import jwt_required_with_body_injection

@router.post("/videos", response_model=TaskResponse, ...)
def create_video(
    background_tasks: BackgroundTasks,
    request: Request,
    body: TaskVideoRequest,
    claims: dict = Depends(jwt_required_with_body_injection),
):
    return create_task(request, body, stop_at="video")
```

```python
# app/controllers/v1/uploads.py
from app.middleware.jwt_auth import jwt_required

@router.post("/uploads/image", ...)
def upload_image(
    request: Request,
    file: UploadFile = File(...),
    role: str | None = Form(None),
    claims: dict = Depends(jwt_required),
):
    ...
```

---

## Verification flow

```python
async def jwt_required(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        # Trust-local-upstream fallback (FR-017)
        if _trust_local_upstream() and request.client and request.client.host == "127.0.0.1":
            return _synthetic_upstream_claims()
        raise HTTPException(
            status_code=401,
            detail={"error_code": "missing_jwt", "detail": "Authorization: Bearer required."},
        )

    token = auth[len("bearer "):].strip()
    try:
        claims = jwt.decode(
            token,
            os.environ["LAYER2_JWT_SIGNING_KEY"],
            algorithms=["HS256"],
            audience="visualai-rendering-engine",
            issuer="visualai-orchestration",
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "expired_jwt", "detail": "Token expired."},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_jwt", "detail": str(exc)},
        )

    tenant_id = claims.get("tenant_id")
    user_id = claims.get("user_id")
    if not tenant_id or not user_id:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_jwt", "detail": "tenant_id or user_id missing"},
        )

    # Set request state
    request.state.tenant_id = tenant_id
    request.state.user_id = user_id
    request.state.request_id = claims.get("jti", "")
    request.state.jwt_claims = claims

    # Bind into Loguru for downstream logging
    # (Loguru's `bind` is request-scoped via contextvars when the route handler
    # runs in a single async coroutine. For thread workers, the dispatcher
    # passes tenant_id + user_id explicitly via VideoParams.)
    logger.bind(
        tenant_id=tenant_id,
        user_id=user_id,
        request_id=request.state.request_id,
    )

    return claims
```

The `_with_body_injection` variant adds:

```python
async def jwt_required_with_body_injection(request: Request) -> dict:
    claims = await jwt_required(request)

    if request.method not in ("POST", "PUT", "PATCH"):
        return claims

    # Read the body, inject tenant_id + user_id, replace stream.
    body_bytes = await request.body()
    if not body_bytes:
        return claims  # empty body — let Pydantic decide
    try:
        body_json = json.loads(body_bytes)
    except json.JSONDecodeError:
        return claims  # not JSON — leave alone (multipart, etc.)

    if isinstance(body_json, dict):
        body_json.setdefault("tenant_id", claims["tenant_id"])
        body_json.setdefault("user_id", claims["user_id"])
        new_body = json.dumps(body_json).encode("utf-8")

        async def receive():
            return {"type": "http.request", "body": new_body, "more_body": False}

        request._receive = receive

    return claims
```

---

## Trust-local-upstream fallback (FR-017)

```python
def _trust_local_upstream() -> bool:
    return os.environ.get("LAYER3_TRUST_LOCAL_UPSTREAM", "false").lower() in ("true", "1", "yes")


def _synthetic_upstream_claims() -> dict:
    return {
        "iss": "visualai-rendering-engine-upstream-trust",
        "aud": "visualai-rendering-engine",
        "tenant_id": "upstream-demo",
        "user_id": "upstream-demo-user",
        "jti": f"upstream-{int(time.time() * 1000)}",
    }
```

When this fallback fires, the controller proceeds as normal. Logs a WARN-level entry every N requests (rate-limited) to make sure ops can see the flag is on.

---

## Production guard (FR-018)

```python
# app/main.py — at app startup
def _verify_production_safety():
    if os.environ.get("LAYER3_ENV", "").lower() == "production":
        if os.environ.get("LAYER3_TRUST_LOCAL_UPSTREAM", "").lower() in ("true", "1", "yes"):
            raise RuntimeError(
                "PRODUCTION SAFETY: LAYER3_TRUST_LOCAL_UPSTREAM=true is forbidden in production"
            )
        signing_key = os.environ.get("LAYER2_JWT_SIGNING_KEY", "")
        if not signing_key or signing_key in ("changeme", "demo", "insecure-default"):
            raise RuntimeError(
                "PRODUCTION SAFETY: LAYER2_JWT_SIGNING_KEY must be set to a real secret"
            )

@app.on_event("startup")
async def startup():
    _verify_production_safety()
```

---

## Test coverage (planned)

| Test | Description |
|---|---|
| JWT-1 | No Authorization header → 401 missing_jwt. |
| JWT-2 | Authorization header with non-Bearer scheme → 401 missing_jwt. |
| JWT-3 | Bearer with malformed token → 401 invalid_jwt. |
| JWT-4 | Bearer signed with wrong key → 401 invalid_jwt. |
| JWT-5 | Bearer with expired token → 401 expired_jwt. |
| JWT-6 | Bearer with wrong issuer → 401 invalid_jwt. |
| JWT-7 | Bearer with wrong audience → 401 invalid_jwt. |
| JWT-8 | Bearer with missing tenant_id claim → 401 invalid_jwt. |
| JWT-9 | Valid bearer → 200; request.state.tenant_id populated. |
| JWT-10 | Valid bearer + JSON body without tenant_id → body gets tenant_id injected before Pydantic parsing (verified by mock controller asserting body.tenant_id == "demo-tenant-001"). |
| JWT-11 | Valid bearer + JSON body WITH tenant_id → middleware preserves the existing value (uses setdefault). |
| JWT-12 | Multipart upload bypass — body NOT modified. |
| JWT-13 | LAYER3_TRUST_LOCAL_UPSTREAM=true + 127.0.0.1 + no Authorization → request accepted with synthetic claims. |
| JWT-14 | LAYER3_TRUST_LOCAL_UPSTREAM=true + 192.168.x.x + no Authorization → still 401 missing_jwt. |
| JWT-15 | LAYER3_TRUST_LOCAL_UPSTREAM=false + 127.0.0.1 + no Authorization → 401 missing_jwt. |
| JWT-16 | Production guard: LAYER3_ENV=production + LAYER3_TRUST_LOCAL_UPSTREAM=true → app fails to start. |
| JWT-17 | Loguru context: log lines emitted during a request include tenant_id + user_id in extras. |
