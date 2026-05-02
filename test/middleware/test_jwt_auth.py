"""Spec 014: JWT middleware tests (JWT-1..JWT-17).

Mocks env vars to use a fixed test signing key. Mints test JWTs via the
same PyJWT lib the middleware uses.
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException, Request

# Set test env BEFORE importing the middleware
TEST_SIGNING_KEY = "test-signing-key-for-jwt-middleware-aaaaaa"
os.environ["LAYER2_JWT_SIGNING_KEY"] = TEST_SIGNING_KEY


from app.middleware.jwt_auth import (  # noqa: E402
    AUDIENCE,
    ISSUER,
    jwt_required,
    jwt_required_with_body_injection,
    verify_production_safety,
)


def _mint_test_jwt(
    *,
    tenant_id: str = "test-tenant",
    user_id: str = "test-user",
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    exp_offset: int = 600,  # 10 minutes from now
    signing_key: str = TEST_SIGNING_KEY,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": user_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "iat": now,
        "exp": now + exp_offset,
        "jti": "test-jti-abc",
    }
    return jwt.encode(claims, signing_key, algorithm="HS256")


def _make_request(headers: dict[str, str] | None = None, host: str = "10.0.0.1") -> Request:
    """Build a minimal mock Request object."""
    from starlette.datastructures import Headers

    raw_headers = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/videos",
        "headers": raw_headers,
        "query_string": b"",
        "client": (host, 12345),
    }
    return Request(scope=scope)


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Each test gets a clean env. Restore the test signing key."""
    monkeypatch.setenv("LAYER2_JWT_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.delenv("LAYER3_TRUST_LOCAL_UPSTREAM", raising=False)
    monkeypatch.delenv("LAYER3_ENV", raising=False)
    yield


@pytest.mark.asyncio
async def test_jwt1_no_authorization_header() -> None:
    """JWT-1: no Authorization header → 401 missing_jwt."""
    request = _make_request(headers={})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.status_code == 401
    assert exc.value.detail["error_code"] == "missing_jwt"


@pytest.mark.asyncio
async def test_jwt2_non_bearer_scheme() -> None:
    """JWT-2: Authorization with non-Bearer scheme → 401 missing_jwt."""
    request = _make_request(headers={"authorization": "Basic foo:bar"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "missing_jwt"


@pytest.mark.asyncio
async def test_jwt3_malformed_token() -> None:
    """JWT-3: malformed token → 401 invalid_jwt."""
    request = _make_request(headers={"authorization": "Bearer not-a-jwt"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "invalid_jwt"


@pytest.mark.asyncio
async def test_jwt4_wrong_signing_key() -> None:
    """JWT-4: token signed with wrong key → 401 invalid_jwt."""
    bad_token = _mint_test_jwt(signing_key="wrong-key-aaaaaaaaaaaaaaaaaaaaaaa")
    request = _make_request(headers={"authorization": f"Bearer {bad_token}"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "invalid_jwt"


@pytest.mark.asyncio
async def test_jwt5_expired_token() -> None:
    """JWT-5: expired token → 401 expired_jwt."""
    expired_token = _mint_test_jwt(exp_offset=-3600)  # 1 hour ago
    request = _make_request(headers={"authorization": f"Bearer {expired_token}"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "expired_jwt"


@pytest.mark.asyncio
async def test_jwt6_wrong_issuer() -> None:
    """JWT-6: wrong iss → 401 invalid_jwt."""
    bad_token = _mint_test_jwt(iss="different-issuer")
    request = _make_request(headers={"authorization": f"Bearer {bad_token}"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "invalid_jwt"


@pytest.mark.asyncio
async def test_jwt7_wrong_audience() -> None:
    """JWT-7: wrong aud → 401 invalid_jwt."""
    bad_token = _mint_test_jwt(aud="someone-else")
    request = _make_request(headers={"authorization": f"Bearer {bad_token}"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "invalid_jwt"


@pytest.mark.asyncio
async def test_jwt8_missing_tenant_id() -> None:
    """JWT-8: claim missing tenant_id → 401 invalid_jwt."""
    now = int(time.time())
    bad_claims = {
        "iss": ISSUER, "aud": AUDIENCE,
        "user_id": "u", "sub": "u",
        "iat": now, "exp": now + 600, "jti": "x",
    }
    bad_token = jwt.encode(bad_claims, TEST_SIGNING_KEY, algorithm="HS256")
    request = _make_request(headers={"authorization": f"Bearer {bad_token}"})
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "invalid_jwt"


@pytest.mark.asyncio
async def test_jwt9_valid_token_sets_request_state() -> None:
    """JWT-9: valid token → request.state populated."""
    token = _mint_test_jwt(tenant_id="my-tenant", user_id="my-user")
    request = _make_request(headers={"authorization": f"Bearer {token}"})
    claims = await jwt_required(request)
    assert claims["tenant_id"] == "my-tenant"
    assert claims["user_id"] == "my-user"
    assert request.state.tenant_id == "my-tenant"
    assert request.state.user_id == "my-user"
    assert request.state.request_id == "test-jti-abc"


@pytest.mark.asyncio
async def test_jwt10_body_injection_adds_tenant_fields() -> None:
    """JWT-10: JSON body without tenant_id gets it injected before parsing."""
    import json

    token = _mint_test_jwt(tenant_id="injected-tenant")
    body_in = json.dumps({"video_subject": "x"}).encode("utf-8")

    raw_headers = [
        (b"authorization", f"Bearer {token}".encode()),
        (b"content-type", b"application/json"),
    ]
    receive_called = {"count": 0}

    async def receive():
        receive_called["count"] += 1
        return {"type": "http.request", "body": body_in, "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/videos",
        "headers": raw_headers, "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope=scope, receive=receive)

    await jwt_required_with_body_injection(request)

    # The request body should now have tenant_id merged in.
    new_body = await request.body()
    parsed = json.loads(new_body)
    assert parsed["tenant_id"] == "injected-tenant"
    assert parsed["video_subject"] == "x"


@pytest.mark.asyncio
async def test_jwt11_body_injection_preserves_existing_tenant_id() -> None:
    """JWT-11: if body already has tenant_id, middleware doesn't overwrite."""
    import json

    token = _mint_test_jwt(tenant_id="from-jwt")
    body_in = json.dumps({"tenant_id": "from-body", "video_subject": "x"}).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body_in, "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/videos",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"", "client": ("127.0.0.1", 12345),
    }
    request = Request(scope=scope, receive=receive)
    await jwt_required_with_body_injection(request)
    new_body = await request.body()
    parsed = json.loads(new_body)
    # setdefault preserves the body's existing value
    assert parsed["tenant_id"] == "from-body"


@pytest.mark.asyncio
async def test_jwt12_multipart_body_not_modified() -> None:
    """JWT-12: multipart bodies pass through without injection."""
    token = _mint_test_jwt()

    async def receive():
        return {"type": "http.request", "body": b"--boundary--", "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/uploads/image",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"multipart/form-data; boundary=boundary"),
        ],
        "query_string": b"", "client": ("127.0.0.1", 12345),
    }
    request = Request(scope=scope, receive=receive)
    await jwt_required_with_body_injection(request)
    body = await request.body()
    assert body == b"--boundary--"  # unchanged


@pytest.mark.asyncio
async def test_jwt13_trust_upstream_local(monkeypatch) -> None:
    """JWT-13: trust-on + 127.0.0.1 + no header → synthetic claims."""
    monkeypatch.setenv("LAYER3_TRUST_LOCAL_UPSTREAM", "true")
    request = _make_request(headers={}, host="127.0.0.1")
    claims = await jwt_required(request)
    assert claims["tenant_id"] == "upstream-demo"


@pytest.mark.asyncio
async def test_jwt14_trust_upstream_non_local_still_rejected(monkeypatch) -> None:
    """JWT-14: trust-on + non-127.0.0.1 + no header → 401."""
    monkeypatch.setenv("LAYER3_TRUST_LOCAL_UPSTREAM", "true")
    request = _make_request(headers={}, host="192.168.1.5")
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "missing_jwt"


@pytest.mark.asyncio
async def test_jwt15_trust_off_local_rejected() -> None:
    """JWT-15: trust-off + 127.0.0.1 + no header → 401 (no fallback)."""
    request = _make_request(headers={}, host="127.0.0.1")
    with pytest.raises(HTTPException) as exc:
        await jwt_required(request)
    assert exc.value.detail["error_code"] == "missing_jwt"


def test_jwt16_production_guard_rejects_trust_on(monkeypatch) -> None:
    """JWT-16: LAYER3_ENV=production + trust-on → fails to start."""
    monkeypatch.setenv("LAYER3_ENV", "production")
    monkeypatch.setenv("LAYER3_TRUST_LOCAL_UPSTREAM", "true")
    monkeypatch.setenv("LAYER2_JWT_SIGNING_KEY", "real-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    with pytest.raises(RuntimeError, match="LAYER3_TRUST_LOCAL_UPSTREAM"):
        verify_production_safety()


def test_jwt16b_production_guard_rejects_placeholder_key(monkeypatch) -> None:
    """JWT-16b: production + placeholder key → fails to start."""
    monkeypatch.setenv("LAYER3_ENV", "production")
    monkeypatch.setenv("LAYER3_TRUST_LOCAL_UPSTREAM", "false")
    monkeypatch.setenv("LAYER2_JWT_SIGNING_KEY", "changeme")
    with pytest.raises(RuntimeError, match="LAYER2_JWT_SIGNING_KEY"):
        verify_production_safety()
