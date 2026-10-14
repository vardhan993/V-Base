"""Shared fixtures for the V-Base backend test suite.

The suite runs against a real PostgreSQL database, never a substitute engine.
By default it uses ``vbase_test`` on the local development container; override
with ``VBASE_TEST_DATABASE_URL`` (for example to point at a Neon branch).

The schema is created by running the project's own Alembic migration, so every
test run also verifies that the migration matches the models.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

logger = logging.getLogger("vbase.tests")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SRC = BACKEND / "src"
for path in (str(ROOT), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

TEST_DATABASE_URL = os.environ.get(
    "VBASE_TEST_DATABASE_URL",
    "postgresql+asyncpg://vbase:vbase_dev_pw@127.0.0.1:5433/vbase_test",
)
ORIGIN = "http://localhost:5173"

# These must be set before nexus.core.config is imported anywhere.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-only-secret-key-please-ignore-0123456789abcdef"
os.environ["FRONTEND_URL"] = ORIGIN
os.environ.setdefault("DB_POOL_SIZE", "2")
os.environ.setdefault("DB_MAX_OVERFLOW", "2")
# Keep the in-process rate limiter from tripping across the whole suite.
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MINUTE", "500")
os.environ.setdefault("RATE_LIMIT_WRITE_PER_MINUTE", "2000")
# The sequence poller is a background loop that sends mail on a timer. Tests
# drive dispatch through the API instead, so no loop should be running.
os.environ.setdefault("SEQUENCES_POLL_ENABLED", "false")

# Imports write the uploaded spreadsheet to disk and backup tests write
# snapshots. Point both at a throwaway directory so a test run never leaves
# files in the repository's uploads/ or backups/ folders.
_TMP_WORKDIR = Path(tempfile.mkdtemp(prefix="vbase-tests-"))
os.environ.setdefault("UPLOADS_DIR", str(_TMP_WORKDIR / "uploads"))
os.environ.setdefault("BACKUPS_DIR", str(_TMP_WORKDIR / "backups"))


def _reset_schema() -> None:
    """Drop and recreate the public schema, then run Alembic to head."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from nexus.core.db import build_connect_args

    url, connect_args = build_connect_args(TEST_DATABASE_URL)

    async def drop_and_create() -> None:
        engine = create_async_engine(url, connect_args=connect_args, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        finally:
            await engine.dispose()

    asyncio.run(drop_and_create())

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")


def _purge_data() -> None:
    """Remove all rows but keep the migrated schema, so tests start clean."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from nexus.core.db import build_connect_args
    from nexus.database import SNAPSHOT_TABLES

    url, connect_args = build_connect_args(TEST_DATABASE_URL)

    async def purge() -> None:
        engine = create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                for table in reversed(SNAPSHOT_TABLES):
                    await conn.execute(text(f'DELETE FROM "{table}"'))
        finally:
            await engine.dispose()

    asyncio.run(purge())


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    """Build the schema once per session via the real migration."""
    try:
        _reset_schema()
    except Exception as exc:  # noqa: BLE001 - any failure means PostgreSQL is unusable for this run
        pytest.skip(f"PostgreSQL is not available at {TEST_DATABASE_URL}: {exc}", allow_module_level=True)
    yield
    from nexus.core.db import dispose_engine

    try:
        asyncio.run(dispose_engine())
    except Exception:
        logger.debug("Disposing the engine during teardown failed", exc_info=True)
    # Remove the per-session uploads/backups scratch directory.
    shutil.rmtree(_TMP_WORKDIR, ignore_errors=True)


@pytest.fixture()
def client(_database):
    """A TestClient that behaves like a browser.

    Browsers always send ``Origin`` on state-changing requests, and the API
    requires the CSRF double-submit token, so both are injected here.
    """
    from fastapi.testclient import TestClient

    from nexus.app import app

    _purge_data()

    class Browser(TestClient):
        def request(self, method, url, **kwargs):  # type: ignore[override]
            headers = {"Origin": ORIGIN}
            csrf = self.cookies.get("vbase_csrf")
            if csrf:
                headers["X-CSRF-Token"] = csrf
            headers.update(kwargs.pop("headers", None) or {})
            kwargs["headers"] = headers
            return super().request(method, url, **kwargs)

    with Browser(app) as test_client:
        yield test_client


@pytest.fixture()
def anonymous_client(_database):
    """A client without CSRF/origin helpers, for negative tests."""
    from fastapi.testclient import TestClient

    from nexus.app import app

    with TestClient(app) as test_client:
        yield test_client


def unique(prefix: str = "t") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def current_head_revision() -> str:
    """Head revision from the Alembic script directory.

    Tests that assert on the revision the API reports use this rather than a
    hard-coded literal: the assertion still proves the database was migrated to
    head, but adding a migration no longer breaks unrelated tests.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def run_sql(sql: str, params: dict | None = None) -> list[dict]:
    """Run raw SQL against the test database on a throwaway connection.

    The application's pooled engine is bound to whichever event loop created
    it (the TestClient runs the app in its own thread), so tests that inspect
    the database directly open their own short-lived connection rather than
    reusing the global engine across event loops.

    Returns the rows as dicts; for statements that return no rows the call is
    committed and an empty list is returned.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from nexus.core.db import build_connect_args

    url, connect_args = build_connect_args(TEST_DATABASE_URL)

    async def execute():
        engine = create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(sql), params or {})
                if not result.returns_rows:
                    return []
                return [dict(row) for row in result.mappings().all()]
        finally:
            await engine.dispose()

    return asyncio.run(execute())


def run_sql_multi(statements: list[str]) -> list[dict]:
    """Run several statements on ONE connection and return the last one's rows.

    Needed for session-scoped statements such as ``SET enable_seqscan = off``
    followed by ``EXPLAIN``, where both must share a connection.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from nexus.core.db import build_connect_args

    url, connect_args = build_connect_args(TEST_DATABASE_URL)

    async def execute():
        engine = create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                rows: list[dict] = []
                for statement in statements:
                    result = await conn.execute(text(statement))
                    rows = [dict(row) for row in result.mappings().all()] if result.returns_rows else []
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(execute())


def sql_scalar(sql: str, params: dict | None = None):
    rows = run_sql(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))


@pytest.fixture()
def auth_client(client):
    """A signed-in client with a unique account."""
    token = unique("user")
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"{token}@example.com",
            "username": token,
            "password": "Str0ngPassw0rd!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture()
def signed_up(client):
    """Returns (client, user_payload) for a freshly created account."""
    token = unique("user")
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"{token}@example.com",
            "username": token,
            "password": "Str0ngPassw0rd!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, response.text
    return client, response.json()
