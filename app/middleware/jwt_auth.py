"""Spec 014: JWT verification middleware for Layer 3 video controllers.

Constitution Principle III (Multi-Tenant Context Propagation) requires every
render request to carry signed tenant context. This middleware verifies a
JWT minted by Layer 2 (the orchestration tier) and binds tenant_id +
user_id into request.state + Loguru's contextvar so downstream code and
log lines pick them up automatically.

Two FastAPI dependency variants:
- ``jwt_required(request)`` — for routes that don't carry a JSON body
  (GET endpoints, multipart upload endpoints). Sets request.state and
  binds Loguru context, but does NOT mutate the body stream.
- ``jwt_required_with_body_injection(request)`` — for JSON-body POST
  endpoints. Reads the body, merges tenant_id + user_id into the JSON,
  and replaces the body stream so downstream Pydantic parsing populates
  VideoParams.tenant_id correctly.

Step-1 transition aid (FR-017): when LAYER3_TRUST_LOCAL_UPSTREAM=true
AND the request is from 127.0.0.1 AND no JWT is present, a synthetic
``upstream-demo`` tenant context is attached. This keeps the legacy
upstream MoneyPrinterTurbo WebUI runnable for local dev without
breaking production hardening.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from loguru import logger

ISSUER = "visualai-orchestration"
AUDIENCE = "visualai-rendering-engine"
_LEEWAY_SECONDS = 30


def _signing_key() -> str:
    key = os.environ.get("LAYER2_JWT_SIGNING_KEY", "")
    if not key:
        raise RuntimeError(
            "LAYER2_JWT_SIGNING_KEY env var not set — required for JWT verification."
        )
    return key


def _trust_local_upstream() -> bool:
    return os.environ.get("LAYER3_TRUST_LOCAL_UPSTREAM", "false").lower() in (
        "true", "1", "yes",
    )


def _is_local_request(request: Request) -> bool:
    if not request.client:
        return False
    # "testclient" is FastAPI's TestClient host. Including it here lets
    # backend tests run without JWT headers when LAYER3_TRUST_LOCAL_UPSTREAM
    # is on, which is fine because the production-guard ensures the trust
    # flag is OFF in production environments.
    return request.client.host in ("127.0.0.1", "::1", "localhost", "testclient")


def _synthetic_upstream_claims() -> dict[str, Any]:
    """Returns synthetic claims attached to local-upstream-trust requests."""
    return {
        "iss": "visualai-rendering-engine-upstream-trust",
        "aud": AUDIENCE,
        "tenant_id": "upstream-demo",
        "user_id": "upstream-demo-user",
        "jti": f"upstream-{int(time.time() * 1000)}",
    }


def _bind_context(request: Request, claims: dict[str, Any]) -> None:
    """Bind tenant context into request.state + Loguru."""
    tenant_id = claims["tenant_id"]
    user_id = claims["user_id"]
    request_id = claims.get("jti", "")

    request.state.tenant_id = tenant_id
    request.state.user_id = user_id
    request.state.request_id = request_id
    request.state.jwt_claims = claims

    # Loguru bind() returns a logger with the bound extra; the request-scoped
    # logger is what handler code should call. For the request-handler thread
    # only — the worker thread re-binds at task start using VideoParams.
    logger.configure(
        extra={"tenant_id": tenant_id, "user_id": user_id, "request_id": request_id}
    )


def _verify_jwt(token: str) -> dict[str, Any]:
    """Decode + validate. Raises HTTPException 401 with typed error_code."""
    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=_LEEWAY_SECONDS,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "expired_jwt", "detail": "Token expired."},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "invalid_jwt", "detail": str(exc)},
        )

    tenant_id = claims.get("tenant_id")
    user_id = claims.get("user_id")
    if not tenant_id or not isinstance(tenant_id, str) or not tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "invalid_jwt", "detail": "tenant_id claim missing/empty."},
        )
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "invalid_jwt", "detail": "user_id claim missing/empty."},
        )

    return claims


async def jwt_required(request: Request) -> dict[str, Any]:
    """FastAPI dependency: verify JWT, set request.state, bind Loguru.

    Honors LAYER3_TRUST_LOCAL_UPSTREAM fallback for local upstream MPT WebUI.
    """
    auth = request.headers.get("authorization", "")

    if not auth or not auth.lower().startswith("bearer "):
        if _trust_local_upstream() and _is_local_request(request):
            claims = _synthetic_upstream_claims()
            _bind_context(request, claims)
            logger.info(
                "trusting local upstream request — synthetic tenant context attached "
                f"(client={request.client.host if request.client else 'unknown'})"
            )
            return claims
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "missing_jwt", "detail": "Authorization: Bearer required."},
        )

    token = auth[len("bearer "):].strip()
    claims = _verify_jwt(token)
    _bind_context(request, claims)
    return claims


async def jwt_required_with_body_injection(request: Request) -> dict[str, Any]:
    """Variant for JSON-body endpoints — also injects tenant_id + user_id
    into the request body so downstream Pydantic models (VideoParams)
    pick them up.

    Multipart bodies are NOT modified; this variant detects them and skips
    injection silently.
    """
    claims = await jwt_required(request)

    if request.method not in ("POST", "PUT", "PATCH"):
        return claims

    content_type = request.headers.get("content-type", "")
    if "multipart" in content_type.lower():
        # Multipart — body is binary; tenant context goes via request.state only.
        return claims

    body_bytes = await request.body()
    if not body_bytes:
        return claims

    try:
        body_json = json.loads(body_bytes)
    except json.JSONDecodeError:
        # Not JSON — leave the body alone.
        return claims

    if not isinstance(body_json, dict):
        return claims

    body_json.setdefault("tenant_id", claims["tenant_id"])
    body_json.setdefault("user_id", claims["user_id"])
    new_body = json.dumps(body_json).encode("utf-8")

    # Replace the cached body AND the receive callable. Starlette caches the
    # first body read in request._body — overwrite it so subsequent body()
    # calls (e.g. by FastAPI's Pydantic parser) see the augmented version.
    request._body = new_body  # type: ignore[attr-defined]

    async def receive():
        return {"type": "http.request", "body": new_body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    return claims


def verify_production_safety() -> None:
    """Hard-fail on insecure flag combinations when LAYER3_ENV=production."""
    if os.environ.get("LAYER3_ENV", "").lower() != "production":
        return
    if _trust_local_upstream():
        raise RuntimeError(
            "PRODUCTION SAFETY: LAYER3_TRUST_LOCAL_UPSTREAM=true is forbidden in production"
        )
    key = os.environ.get("LAYER2_JWT_SIGNING_KEY", "")
    if not key or key in (
        "changeme-generate-via-openssl-rand-hex-32",
        "changeme",
        "demo",
        "insecure-default",
    ):
        raise RuntimeError(
            "PRODUCTION SAFETY: LAYER2_JWT_SIGNING_KEY must be set to a real secret"
        )
