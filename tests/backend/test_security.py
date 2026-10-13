"""Security tests: CSRF, origin validation, sessions, auth guards and rate limiting."""

from __future__ import annotations

import pytest

from nexus.core.db import build_connect_args

from .conftest import ORIGIN, unique

# ---------------------------------------------------------------------------
# Origin / CSRF
# ---------------------------------------------------------------------------


def test_write_without_origin_is_rejected(anonymous_client):
    response = anonymous_client.post(
        "/api/v1/auth/signup",
        json={"email": "csrf@example.com", "username": "csrfuser", "password": "Str0ngPassw0rd!"},
    )
    assert response.status_code == 403
    assert "Origin" in response.json()["detail"]


def test_write_from_foreign_origin_is_rejected(anonymous_client):
    response = anonymous_client.post(
        "/api/v1/auth/signup",
        headers={"Origin": "https://evil.example"},
        json={"email": "csrf2@example.com", "username": "csrfuser2", "password": "Str0ngPassw0rd!"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Origin not allowed"


def test_write_without_csrf_token_is_rejected(client):
    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    # Session cookie exists, but the double-submit token is missing.
    response = client.post("/api/v1/companies", headers={"X-CSRF-Token": ""}, json={"name": "No CSRF"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_mismatched_csrf_token_is_rejected(client):
    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    response = client.post(
        "/api/v1/companies", headers={"X-CSRF-Token": "not-the-real-token"}, json={"name": "Bad CSRF"}
    )
    assert response.status_code == 403


def test_authorised_write_succeeds(auth_client):
    response = auth_client.post("/api/v1/companies", json={"name": unique("Allowed")})
    assert response.status_code == 201


def test_reads_do_not_require_origin(auth_client):
    """GET requests are not CSRF-protected, so they must work without Origin."""
    assert auth_client.get("/api/v1/companies").status_code == 200


# ---------------------------------------------------------------------------
# Authentication and authorisation
# ---------------------------------------------------------------------------

PROTECTED_ROUTES = [
    ("get", "/api/v1/companies"),
    ("get", "/api/v1/contacts"),
    ("get", "/api/v1/lists"),
    ("get", "/api/v1/tags"),
    ("get", "/api/v1/analytics/overview"),
    ("get", "/api/v1/activity"),
    ("get", "/api/v1/settings/app"),
    ("get", "/api/v1/settings/preferences"),
    ("get", "/api/v1/import/history"),
    ("get", "/api/v1/duplicates"),
    ("get", "/api/v1/views"),
    ("get", "/api/v1/custom-fields"),
    ("get", "/api/v1/users"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_protected_routes_require_a_session(anonymous_client, method, path):
    response = getattr(anonymous_client, method)(path)
    assert response.status_code == 401, f"{path} returned {response.status_code}"


def test_forged_session_cookie_is_rejected(anonymous_client):
    anonymous_client.cookies.set("vbase_session", "totally-made-up-token")
    response = anonymous_client.get("/api/v1/companies")
    assert response.status_code == 401


def test_superuser_only_routes_are_enforced(auth_client):
    assert auth_client.get("/api/v1/users").status_code == 403
    assert auth_client.get("/api/v1/users/1").status_code == 403
    assert auth_client.post("/api/v1/auth/cleanup-sessions").status_code == 403


def test_signup_cannot_self_assign_superuser(anonymous_client):
    token = unique("user")
    response = anonymous_client.post(
        "/api/v1/auth/signup",
        headers={"Origin": ORIGIN},
        json={
            "email": f"{token}@example.com",
            "username": token,
            "password": "Str0ngPassw0rd!",
            "is_superuser": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["user_id"] > 0
    me = anonymous_client.get("/api/v1/auth/me")
    assert me.json()["is_superuser"] is False


def test_password_change_revokes_other_sessions(client):
    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 1 and sessions[0]["current"] is True

    changed = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Str0ngPassw0rd!",
            "new_password": "EvenStr0nger!",
            "confirm_password": "EvenStr0nger!",
        },
    )
    assert changed.status_code == 200, changed.text

    # Old password no longer works, new one does.
    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": f"{token}@example.com", "password": "Str0ngPassw0rd!"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": f"{token}@example.com", "password": "EvenStr0nger!"}
        ).status_code
        == 200
    )


def test_session_tokens_are_hashed_at_rest(signed_up):
    """The raw cookie value must never appear in the sessions table."""
    import hashlib

    from .conftest import run_sql

    client, _ = signed_up
    raw_token = client.cookies.get("vbase_session")
    assert raw_token

    stored = [row["token_hash"] for row in run_sql("SELECT token_hash FROM sessions")]
    assert stored, "expected at least one session row"
    assert raw_token not in stored
    assert hashlib.sha256(raw_token.encode()).hexdigest() in stored


def test_logout_revokes_the_session_row(client):
    from .conftest import sql_scalar

    token = unique("user")
    client.post(
        "/api/v1/auth/signup",
        json={"email": f"{token}@example.com", "username": token, "password": "Str0ngPassw0rd!"},
    )
    client.post("/api/v1/auth/logout")

    assert sql_scalar("SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL") >= 1


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limiter_returns_429_with_retry_after():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from nexus.core.middleware import RateLimitMiddleware

    async def login(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/v1/auth/login", login, methods=["POST"])])
    app.add_middleware(RateLimitMiddleware, limits={"auth": 3, "write": 100})

    with TestClient(app) as test_client:
        for _ in range(3):
            assert test_client.post("/api/v1/auth/login").status_code == 200
        blocked = test_client.post("/api/v1/auth/login")
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"].isdigit()


def test_session_probes_are_not_in_the_credential_bucket():
    """GET /auth/me runs on every page load, so it must not share login's ceiling.

    Regression test: with /auth/me in the tight bucket, a normal navigation
    burst returned 429 and the SPA could never establish whether a session
    existed.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from nexus.core.middleware import RateLimitMiddleware

    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/v1/auth/me", ok, methods=["GET"]),
            Route("/api/v1/auth/login", ok, methods=["POST"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, limits={"auth": 2, "session": 50, "write": 100})

    with TestClient(app) as test_client:
        for _ in range(20):
            assert test_client.get("/api/v1/auth/me").status_code == 200

        # The credential endpoint keeps its own, much tighter ceiling.
        assert test_client.post("/api/v1/auth/login").status_code == 200
        assert test_client.post("/api/v1/auth/login").status_code == 200
        assert test_client.post("/api/v1/auth/login").status_code == 429


def test_rate_limiter_does_not_count_reads():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from nexus.core.middleware import RateLimitMiddleware

    async def listing(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/v1/companies", listing, methods=["GET"])])
    app.add_middleware(RateLimitMiddleware, limits={"auth": 1, "write": 1})

    with TestClient(app) as test_client:
        for _ in range(50):
            assert test_client.get("/api/v1/companies").status_code == 200


# ---------------------------------------------------------------------------
# Configuration and connection-string handling
# ---------------------------------------------------------------------------


def test_non_postgres_url_is_rejected():
    """SQLite (and any other engine) must be refused at configuration time."""
    from pydantic import ValidationError

    from nexus.core.config import Settings

    with pytest.raises(ValidationError, match="must be a PostgreSQL DSN"):
        Settings(database_url="sqlite+aiosqlite:///./vbase.db")


def test_sslmode_is_translated_for_asyncpg():

    url, connect_args = build_connect_args(
        "postgresql+asyncpg://user:pw@ep-test.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    )
    # asyncpg has no `sslmode` kwarg: it must be removed and converted.
    assert "sslmode=" not in url
    assert connect_args["ssl"] is not None
    assert connect_args["server_settings"]["application_name"] == "vbase-api"


def test_transaction_pooler_disables_prepared_statement_cache():
    from nexus.core.db import is_transaction_pooler

    pooler = "postgresql+asyncpg://user:pw@ep-test-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    assert is_transaction_pooler(pooler) is True
    _, connect_args = build_connect_args(pooler)
    assert connect_args["statement_cache_size"] == 0

    # A direct endpoint keeps the pooled prepared-statement cache.
    assert is_transaction_pooler("postgresql+asyncpg://user:pw@db.example.com:5432/vbase") is False
    _, direct_args = build_connect_args("postgresql+asyncpg://user:pw@db.example.com:5432/vbase")
    assert direct_args["statement_cache_size"] > 0


def test_unsupported_dsn_params_are_dropped_or_mapped():

    url, connect_args = build_connect_args(
        "postgresql+asyncpg://user:pw@host/db"
        "?sslmode=require&channel_binding=require&connect_timeout=10&application_name=vbase-test"
    )
    # Dropped: asyncpg has no equivalent kwarg and they must not reach connect().
    assert "channel_binding" not in url
    assert "connect_timeout" not in url
    # Mapped to the asyncpg spelling.
    assert connect_args["timeout"] == 10.0
    assert "application_name" not in url
    assert connect_args["server_settings"]["application_name"] == "vbase-test"


def test_production_requires_secure_configuration():
    from nexus.core.config import INSECURE_SECRET, Settings

    insecure = Settings(environment="production", secret_key=INSECURE_SECRET, database_url=Settings().database_url)
    with pytest.raises(RuntimeError):
        insecure.validate_production()


def test_security_headers_are_present(auth_client):
    response = auth_client.get("/api/v1/companies")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["x-request-id"]


def test_request_id_is_echoed_back(client):
    response = client.get("/health", headers={"X-Request-Id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
