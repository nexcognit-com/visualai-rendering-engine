"""Shared pytest config — runs before any test in test/.

Sets ``LAYER3_TRUST_LOCAL_UPSTREAM=true`` so existing TestClient-based
tests (test/controllers/*) keep working without JWT headers. The
production-guard test cases (test/middleware/test_jwt_auth.py) set
their own env via monkeypatch, so this default doesn't interfere.

Spec 014 follow-up: when we want to test JWT-bearing flows specifically,
use the ``auth_headers`` fixture in test/controllers/conftest.py (todo).
"""

from __future__ import annotations

import os

# Default to trust-local-upstream so the existing test suite keeps passing.
# Individual tests that need to disable it monkeypatch their own env.
os.environ.setdefault("LAYER3_TRUST_LOCAL_UPSTREAM", "true")
os.environ.setdefault("LAYER2_JWT_SIGNING_KEY", "test-signing-key-32-chars-long-aaaaaa")
