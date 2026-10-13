from __future__ import annotations

import logging
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from nexus.core.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None

#: Query-string parameters that asyncpg.connect() accepts directly.
_ASYNCPG_URL_PARAMS = {"ssl", "server_settings", "statement_cache_size", "timeout", "command_timeout"}

#: libpq DSN parameters that have a different asyncpg name, or that belong in
#: server_settings. Everything not listed here is dropped (with a warning)
#: rather than forwarded, because asyncpg raises TypeError on unknown kwargs.
_DSN_PARAM_MAP = {
    "connect_timeout": "timeout",
    "application_name": "server_settings.application_name",
    "sslrootcert": "ssl_ca_file",
    "sslcert": "ssl_cert_file",
    "sslkey": "ssl_key_file",
}

#: Parameters that are safe to ignore silently (they describe client-side
#: behaviour asyncpg handles internally).
_DSN_PARAM_IGNORED = {
    "channel_binding",
    "target_session_attrs",
    "options",
    "keepalives",
    "keepalives_idle",
    "keepalives_interval",
    "keepalives_count",
    "gssencmode",
    "sslnegotiation",
    "sslcertmode",
    "ssl_min_protocol_version",
    "ssl_max_protocol_version",
    "tcp_user_timeout",
}


def is_transaction_pooler(database_url: str) -> bool:
    """True when the DSN points at a PgBouncer running in transaction mode."""
    url = make_url(database_url)
    host = (url.host or "").lower()
    port = url.port or 5432
    if "-pooler" in host or ".pooler." in host:
        return True
    # Supabase's shared transaction pooler listens on 6543.
    return port == 6543


def build_connect_args(database_url: str) -> tuple[str, dict[str, Any]]:
    """Translate a libpq-style DSN into an asyncpg-friendly URL + connect args.

    Managed providers hand out DSNs with ``?sslmode=require`` (Neon, Supabase,
    Aiven) and sometimes ``channel_binding=require``. SQLAlchemy forwards
    unknown query parameters straight to ``asyncpg.connect()``, which rejects
    them with a TypeError, so each one is translated or dropped here.
    """
    url = make_url(database_url)
    query = dict(url.query)
    connect_args: dict[str, Any] = {}

    sslmode = str(query.pop("sslmode", "")).lower()
    ssl_files = {key: query.pop(key, None) for key in ("sslrootcert", "sslcert", "sslkey")}

    if sslmode in {"require", "prefer", "allow"}:
        # Encrypt the transport. Managed providers terminate TLS with a public
        # certificate chain, but "require" explicitly does not verify it, and
        # verifying would break the documented Neon/Supabase setup.
        context = ssl.create_default_context()
        if ssl_files.get("sslrootcert"):
            context.load_verify_locations(ssl_files["sslrootcert"])
        else:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        if ssl_files.get("sslcert"):
            context.load_cert_chain(ssl_files["sslcert"], ssl_files.get("sslkey"))
        connect_args["ssl"] = context
    elif sslmode in {"verify-ca", "verify-full"}:
        context = ssl.create_default_context(cafile=ssl_files.get("sslrootcert"))
        connect_args["ssl"] = context
    elif sslmode in {"disable", "allow"}:
        connect_args["ssl"] = False

    server_settings: dict[str, str] = {}
    unsupported: list[str] = []
    for key in list(query):
        value = query.pop(key)
        if key in _ASYNCPG_URL_PARAMS:
            if key == "server_settings" and isinstance(value, dict):
                server_settings.update({str(k): str(v) for k, v in value.items()})
            else:
                connect_args[key] = value
            continue
        if key in _DSN_PARAM_IGNORED:
            continue
        target = _DSN_PARAM_MAP.get(key)
        if target is None:
            unsupported.append(key)
            continue
        if target.startswith("server_settings."):
            server_settings[target.split(".", 1)[1]] = str(value)
        elif target == "timeout":
            connect_args.setdefault("timeout", float(value))

    if unsupported:
        logger.warning("Ignoring DSN parameters not supported by asyncpg: %s", ", ".join(sorted(unsupported)))

    if "statement_cache_size" not in connect_args and is_transaction_pooler(database_url):
        # Prepared statements cannot be reused across server connections behind
        # a transaction pooler; asyncpg would raise "prepared statement already
        # exists" or return results from the wrong connection.
        connect_args["statement_cache_size"] = 0
    connect_args.setdefault("statement_cache_size", settings.db_statement_cache_size)

    connect_args.setdefault("command_timeout", settings.db_command_timeout)

    server_settings.setdefault("application_name", "vbase-api")
    # Deterministic plans for the small, repetitive queries the app issues.
    server_settings.setdefault("jit", "off")
    connect_args["server_settings"] = server_settings

    return url.set(query=query).render_as_string(hide_password=False), connect_args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def _create_engine() -> AsyncEngine:
    url, connect_args = build_connect_args(settings.database_url)
    pool_kwargs: dict[str, Any] = {}
    if settings.db_use_null_pool:
        pool_kwargs["poolclass"] = NullPool
    else:
        pool_kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
        )

    logger.info(
        "Creating PostgreSQL engine (pool=%s size=%s overflow=%s ssl=%s statement_cache_size=%s transaction_pooler=%s)",
        "null" if settings.db_use_null_pool else "queue",
        settings.db_pool_size,
        settings.db_max_overflow,
        bool(connect_args.get("ssl")),
        connect_args.get("statement_cache_size"),
        is_transaction_pooler(settings.database_url),
    )
    return create_async_engine(
        url,
        echo=settings.db_echo,
        # Neon and Supabase suspend idle compute; a pooled connection can be
        # dead before SQLAlchemy notices. pre_ping replaces it transparently.
        pool_pre_ping=True,
        connect_args=connect_args,
        future=True,
        **pool_kwargs,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Verify the PostgreSQL connection and that migrations have been applied."""
    engine = get_engine()
    async with engine.connect() as conn:
        version = (await conn.execute(text("SHOW server_version"))).scalar()
        try:
            revision = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        except Exception:
            revision = None
    if revision is None:
        raise RuntimeError("PostgreSQL is reachable but the schema is missing. Run: alembic upgrade head")
    logger.info("PostgreSQL %s ready (alembic revision %s)", version, revision)


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def database_health() -> dict[str, Any]:
    """Cheap liveness probe used by /health/ready."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            one = (await conn.execute(text("SELECT 1"))).scalar()
        pool = engine.pool
        return {
            "status": "ok" if one == 1 else "degraded",
            "pool": {
                "size": getattr(pool, "size", lambda: None)(),
                "checked_out": getattr(pool, "checkedout", lambda: None)(),
                "overflow": getattr(pool, "overflow", lambda: None)(),
            },
        }
    except Exception as exc:  # pragma: no cover - reported to the caller
        logger.warning("Database health check failed: %s", exc)
        return {"status": "error", "error": type(exc).__name__}


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Transactional scope for scripts and background work."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session without implicit commit.

    Routes commit explicitly where they mutate data. Committing from the
    dependency would mask errors and double-commit after an explicit commit.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
