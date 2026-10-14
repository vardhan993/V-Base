from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import client_ip, get_current_user, require_superuser
from nexus.core.audit import record_activity
from nexus.core.config import settings
from nexus.core.db import get_session
from nexus.core.pg_binaries import pg_client_env, resolve_pg_binary
from nexus.database import SNAPSHOT_TABLES, Base, SettingsRow

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _stamp() -> str:
    return _utcnow().strftime("%Y%m%d_%H%M%S")


def _pg_dump_binary() -> str | None:
    """Resolved path to ``pg_dump`` (PATH, then standard install dirs)."""
    return resolve_pg_binary("pg_dump", settings.pg_dump_path)


def _pg_dump_available() -> bool:
    return _pg_dump_binary() is not None


def _db_size_bytes() -> int | None:
    """Size of the connected database, straight from PostgreSQL."""
    return None  # filled in by the async helper below


async def _database_size(session: AsyncSession) -> int | None:
    try:
        return int((await session.execute(text("SELECT pg_database_size(current_database())"))).scalar() or 0)
    except Exception:
        return None


async def _database_summary(session: AsyncSession) -> dict[str, Any]:
    version = (await session.execute(text("SHOW server_version"))).scalar()
    revision = None
    try:
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    except Exception:
        pass
    return {
        "server_version": version,
        "alembic_revision": revision,
        "size_bytes": await _database_size(session),
        "host": _safe_host(),
    }


def _safe_host() -> str | None:
    """Host portion of the DSN with all credentials stripped."""
    try:
        from sqlalchemy.engine import make_url

        return make_url(settings.database_url).host
    except Exception:
        return None


# ---------------------------------------------------------------------------
# App info & preferences
# ---------------------------------------------------------------------------


@router.get("/settings/app")
async def app_info(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    return {
        "app_name": settings.app_name,
        "tagline": settings.tagline,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": await _database_summary(session),
        "database_engine": "postgresql",
        "uploads_path": str(settings.uploads_path),
        "backups_path": str(settings.backups_path),
        "pg_dump_available": _pg_dump_available(),
        "pg_dump_binary": _pg_dump_binary(),
        "last_backup": await _last_backup_date(session),
    }


@router.get("/settings/keys")
async def list_settings_keys(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    rows = list((await session.execute(select(SettingsRow).order_by(SettingsRow.key))).scalars().all())
    return [
        {"key": r.key, "value": r.value, "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows
    ]


@router.post("/settings/keys", status_code=status.HTTP_201_CREATED)
async def set_setting(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    key = (body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key required")
    await _upsert_setting(session, key, body.get("value"), current_user.id)
    await session.commit()
    return {"key": key, "value": body.get("value")}


@router.get("/settings/preferences")
async def get_preferences(current_user=Depends(get_current_user)):
    return current_user.preferences or {}


@router.patch("/settings/preferences")
async def update_preferences(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    # SQLAlchemy does not detect in-place mutation of a JSONB dict, so the
    # whole value is rebuilt and reassigned to guarantee the UPDATE fires.
    merged = {**(current_user.preferences or {}), **body}
    current_user.preferences = merged
    await session.commit()
    await session.refresh(current_user)
    return current_user.preferences


# ---------------------------------------------------------------------------
# Backup & restore
# ---------------------------------------------------------------------------
#
# Two complementary mechanisms, both free:
#
# * Logical JSON snapshot (default, always available). Reads every table in
#   SNAPSHOT_TABLES and writes one JSON document. Restoring replays it inside a
#   single transaction with every constraint checked at COMMIT. This is the
#   portable path: it needs no binaries on the host, which matters on Render's
#   free plan and Neon.
# * Physical SQL dump via ``pg_dump`` (used when the binary is present). This
#   is the same artifact ``pg_restore`` consumes, and the recommended route for
#   a full instance-level recovery.
#
# For Neon specifically, point-in-time restore (6 hours on Free) is also
# available from the console; see docs/BACKUP.md.


@router.post("/settings/backup", status_code=status.HTTP_201_CREATED)
async def create_backup(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    backup_dir = settings.backups_path
    backup_dir.mkdir(parents=True, exist_ok=True)
    kind = "json"
    name = f"vbase_snapshot_{_stamp()}.json"

    if _pg_dump_available():
        name = f"vbase_dump_{_stamp()}.sql"
        dest = backup_dir / name
        try:
            _run_pg_dump(dest)
            kind = "pg_dump"
        except Exception as exc:  # fall back rather than fail the request
            logger.warning("pg_dump failed (%s); falling back to a JSON snapshot", exc)
            name = f"vbase_snapshot_{_stamp()}.json"
            kind = "json"

    dest = backup_dir / name
    if kind == "json":
        payload = await _export_snapshot(session)
        dest.write_text(json.dumps(payload), encoding="utf-8")

    if not dest.exists() or dest.stat().st_size == 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Backup file was not created")

    validation = _validate_backup(dest, kind)
    if not validation["valid"]:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup validation failed: {validation['error']}",
        )

    await _upsert_setting(
        session, "last_backup", {"file": str(dest), "kind": kind, "created_at": _utcnow().isoformat()}, current_user.id
    )
    await record_activity(
        session,
        action="backup_created",
        user_id=current_user.id,
        entity_type="database",
        description=f"{kind} backup written to {name}",
        metadata={"file": name, "kind": kind, "bytes": dest.stat().st_size},
        ip_address=client_ip(request),
    )
    await session.commit()
    return {
        "backup_file": str(dest),
        "name": name,
        "kind": kind,
        "size_bytes": dest.stat().st_size,
        "database": await _database_summary(session),
    }


@router.get("/settings/backups")
async def list_backups(current_user=Depends(get_current_user)):
    backup_dir = settings.backups_path
    backup_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for f in sorted(
        [*backup_dir.glob("*.json"), *backup_dir.glob("*.sql")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            st = f.stat()
            kind = "pg_dump" if f.suffix == ".sql" else "json"
            items.append(
                {
                    "file": str(f),
                    "name": f.name,
                    "kind": kind,
                    "size_bytes": st.st_size,
                    "created_at": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                    "validation": _validate_backup(f, kind),
                }
            )
        except OSError:
            continue
    return {
        "backups": items,
        "count": len(items),
        "backups_path": str(backup_dir),
        "pg_dump_available": _pg_dump_available(),
    }


@router.post("/settings/backup/verify")
async def verify_backup(body: dict[str, str], current_user=Depends(get_current_user)):
    src = _resolve_backup(body.get("backup_file") or "")
    kind = "pg_dump" if src.suffix == ".sql" else "json"
    return {"file": str(src), "kind": kind, "validation": _validate_backup(src, kind)}


@router.post("/settings/restore", status_code=status.HTTP_200_OK)
async def restore_backup(
    request: Request,
    body: dict[str, str],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(require_superuser),
):
    """Restore from a JSON snapshot, or return instructions for a SQL dump.

    JSON restores are transactional: every row is re-inserted and the sequence
    counters are reset, all inside one transaction. Any constraint violation
    rolls the whole restore back, so a partially applied restore is impossible.
    SQL dumps are handed to ``pg_restore``/``psql`` guidance instead, because
    running them in-process would bypass the app's own transaction handling.
    """
    src = _resolve_backup(body.get("backup_file") or "")
    kind = "pg_dump" if src.suffix == ".sql" else "json"
    validation = _validate_backup(src, kind)
    if not validation["valid"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation["error"])

    if kind == "pg_dump":
        return {
            "status": "manual_action_required",
            "kind": kind,
            "file": str(src),
            "instructions": (
                "Restore this SQL dump with the pg_restore/psql command documented in "
                "docs/BACKUP.md. It is deliberately not executed by the API so a "
                "migration/orchestration step stays in control."
            ),
        }

    payload = json.loads(src.read_text(encoding="utf-8"))
    safety = settings.backups_path / f"pre_restore_{_stamp()}.json"
    safety.write_text(json.dumps(await _export_snapshot(session)), encoding="utf-8")

    restored = await _restore_snapshot(session, payload)
    await _upsert_setting(
        session, "last_restore", {"file": str(src), "restored_at": _utcnow().isoformat()}, current_user.id
    )
    await record_activity(
        session,
        action="backup_restored",
        user_id=current_user.id,
        entity_type="database",
        description=f"Restored {restored} row(s) from {src.name}",
        metadata={"file": src.name, "rows": restored, "safety_snapshot": str(safety)},
        ip_address=client_ip(request),
    )
    await session.commit()
    return {
        "status": "restored",
        "restored_from": str(src),
        "rows_restored": restored,
        "safety_snapshot": str(safety),
        "note": "Sessions were preserved, so no re-login is required.",
    }


@router.get("/settings/export-db")
async def export_database(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Describe the export, plus a portable JSON dump inline."""
    return {
        "database": await _database_summary(session),
        "tables": list(SNAPSHOT_TABLES),
        "download_url": "/api/v1/settings/download-db",
        "pg_dump_command": _pg_dump_command_preview(),
    }


@router.get("/settings/download-db")
async def download_database(session: AsyncSession = Depends(get_session), current_user=Depends(get_current_user)):
    """Stream a JSON snapshot of the whole database as a download."""
    payload = await _export_snapshot(session)
    dest = settings.backups_path / f"vbase_export_{_stamp()}.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")
    return FileResponse(path=dest, filename=dest.name, media_type="application/json")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pg_dump_command_preview() -> str:
    """Human-readable pg_dump invocation with the password redacted."""
    from sqlalchemy.engine import make_url

    try:
        url = make_url(settings.database_url)
    except Exception:
        return "pg_dump --format=custom <DATABASE_URL>"
    host = f"{url.host}:{url.port or 5432}"
    return (
        f"pg_dump --format=custom --no-owner --no-privileges "
        f"--host={host} --username={url.username} --dbname={url.database} "
        f"--file=backup.dump   # credentials supplied via the environment"
    )


def _run_pg_dump(dest: Path) -> None:
    """Run pg_dump into ``dest``. Raises on any failure."""
    from sqlalchemy.engine import make_url

    binary = _pg_dump_binary()
    if binary is None:
        raise RuntimeError("pg_dump was not found on PATH or in the standard PostgreSQL install locations")

    url = make_url(settings.database_url)
    env = pg_client_env(binary, password=url.password, sslmode=url.query.get("sslmode"))
    cmd = [
        binary,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--host={url.host or 'localhost'}",
        f"--port={url.port or 5432}",
        f"--username={url.username}",
        f"--dbname={url.database}",
        "--file",
        str(dest),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:500] or f"pg_dump exited {proc.returncode}")


def _resolve_backup(backup_file: str) -> Path:
    if not backup_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="backup_file required")
    src = Path(backup_file)
    try:
        # Path traversal guard: only files inside the backups directory.
        src.resolve().relative_to(settings.backups_path.resolve())
    except ValueError as exc:
        # relative_to raises ValueError when the path escapes the backups root.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Backup must be inside the backups directory"
        ) from exc
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not found")
    return src


def _validate_backup(path: Path, kind: str) -> dict[str, Any]:
    """Actually parse the artifact. No silent success."""
    try:
        if kind == "pg_dump":
            header = path.read_bytes()[:5]
            if header != b"PGDMP":
                return {"valid": False, "error": "Not a pg_dump custom-format archive"}
            size = path.stat().st_size
            return {"valid": True, "format": "pg_dump-custom", "size_bytes": size}

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "tables" not in payload:
            return {"valid": False, "error": "Snapshot is missing the 'tables' section"}
        tables = payload["tables"]
        if not isinstance(tables, dict):
            return {"valid": False, "error": "'tables' must be an object"}
        unknown = sorted(set(tables) - set(SNAPSHOT_TABLES))
        row_count = sum(len(v) for v in tables.values() if isinstance(v, list))
        return {
            "valid": True,
            "format": "json-snapshot",
            "schema_version": payload.get("schema_version"),
            "tables": len(tables),
            "rows": row_count,
            "unknown_tables": unknown,
        }
    except json.JSONDecodeError as exc:
        return {"valid": False, "error": f"Invalid JSON: {exc}"}
    except OSError as exc:
        return {"valid": False, "error": f"Unreadable: {exc}"}


async def _export_snapshot(session: AsyncSession) -> dict[str, Any]:
    """Read every table into a JSON-serialisable document."""
    revision = None
    try:
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    except Exception:
        pass

    tables: dict[str, list[dict[str, Any]]] = {}
    for table in SNAPSHOT_TABLES:
        if table == "sessions":
            # Session tokens are deliberately excluded from exports: a backup
            # file must never contain material that authenticates a user.
            continue
        rows = (await session.execute(text(f'SELECT * FROM "{table}"'))).mappings().all()
        tables[table] = [_jsonable(dict(row)) for row in rows]

    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "schema_version": revision,
        "created_at": _utcnow().isoformat(),
        "engine": "postgresql",
        "tables": tables,
        "row_counts": {name: len(rows) for name, rows in tables.items()},
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


async def _restore_snapshot(session: AsyncSession, payload: dict[str, Any]) -> int:
    """Replace table contents with the snapshot, inside one transaction.

    Delete and re-insert happen in a single transaction, so a failure at any
    point leaves the database exactly as it was. Two details matter:

    * Generated columns (``search_vector``) are read by ``SELECT *`` but cannot
      be written, so they are skipped on the way back in.
    * Values arrive from JSON as strings and numbers. Each placeholder is cast
      to the target column's own PostgreSQL type, which is what lets a
      timestamp text value land in a ``timestamptz`` column.

    Session rows are captured before the users table is replaced and written
    back afterwards, so a restore does not sign every user out.
    """
    tables = payload.get("tables") or {}
    unknown = sorted(set(tables) - set(SNAPSHOT_TABLES))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Snapshot contains unknown tables: {', '.join(unknown)}",
        )

    # Replacing `users` cascades to `sessions`; keep them to preserve logins.
    sessions_backup = [dict(row) for row in (await session.execute(text("SELECT * FROM sessions"))).mappings().all()]

    from sqlalchemy.dialects import postgresql as pg_dialect

    dialect = pg_dialect.dialect()
    # Children before parents on the way in, so FK constraints stay satisfied.
    ordered = [t for t in reversed(SNAPSHOT_TABLES) if t in tables]
    inserted = 0

    for table in ordered:
        rows = tables.get(table) or []
        await session.execute(text(f'DELETE FROM "{table}"'))

        table_meta = Base.metadata.tables.get(table)
        if table_meta is None:  # pragma: no cover - guarded by SNAPSHOT_TABLES
            continue
        writable = {col.name: col for col in table_meta.columns if col.computed is None}

        for row in rows:
            columns = [name for name in row if name in writable]
            if not columns:
                continue
            col_sql = ", ".join(f'"{c}"' for c in columns)
            placeholders = []
            bind: dict[str, Any] = {}
            for index, name in enumerate(columns):
                key = f"v{index}"
                column = writable[name]
                pg_type = column.type.compile(dialect=dialect)
                placeholders.append(f"CAST(:{key} AS {pg_type})")
                bind[key] = _coerce_for_db(row[name], column.type)
            value_sql = ", ".join(placeholders)
            await session.execute(
                text(f'INSERT INTO "{table}" ({col_sql}) VALUES ({value_sql})'),
                bind,
            )
            inserted += 1

    if sessions_backup:
        for row in sessions_backup:
            columns = list(row.keys())
            col_sql = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(
                f"CAST(:v{i} AS {_pg_type_for('sessions', name, dialect)})" for i, name in enumerate(columns)
            )
            bind = {
                f"v{i}": _coerce_for_db(value, _column_type("sessions", name))
                for i, (name, value) in enumerate(row.items())
            }
            await session.execute(
                text(f"INSERT INTO sessions ({col_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"),
                bind,
            )

    await _reset_sequences(session)
    return inserted


def _column_type(table: str, column: str) -> Any:
    table_meta = Base.metadata.tables.get(table)
    if table_meta is not None and column in table_meta.columns:
        return table_meta.columns[column].type
    return None


def _pg_type_for(table: str, column: str, dialect: Any) -> str:
    column_type = _column_type(table, column)
    return column_type.compile(dialect=dialect) if column_type is not None else "text"


def _coerce_for_db(value: Any, column_type: Any = None) -> Any:
    """Turn a JSON snapshot value back into what asyncpg expects for the column.

    JSON has no date, timestamp or object types, so these are rebuilt here:
    timestamps become ``datetime`` (asyncpg refuses a string for a
    ``timestamptz`` parameter) and objects/arrays are re-serialised for JSONB.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, str) and column_type is not None:
        from sqlalchemy import Date, DateTime

        try:
            if isinstance(column_type, DateTime):
                return datetime.fromisoformat(value)
            if isinstance(column_type, Date):
                return datetime.fromisoformat(value).date()
        except ValueError:
            return value
    return value


async def _reset_sequences(session: AsyncSession) -> None:
    """Realign every identity sequence with its table's current maximum."""
    for table in SNAPSHOT_TABLES:
        try:
            await session.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f'COALESCE((SELECT MAX(id) FROM "{table}"), 1), '
                    f'(SELECT MAX(id) IS NOT NULL FROM "{table}"))'
                )
            )
        except Exception:
            continue


async def _upsert_setting(session: AsyncSession, key: str, value: Any, user_id: int | None) -> None:
    existing = (await session.execute(select(SettingsRow).where(SettingsRow.key == key))).scalar_one_or_none()
    if existing:
        existing.value = value
        existing.updated_by_id = user_id
    else:
        session.add(SettingsRow(key=key, value=value, updated_by_id=user_id))


async def _last_backup_date(session: AsyncSession) -> str | None:
    try:
        row = (await session.execute(select(SettingsRow).where(SettingsRow.key == "last_backup"))).scalar_one_or_none()
        if not row or not row.value:
            return None
        value = row.value
        return value.get("created_at") if isinstance(value, dict) else str(value)
    except Exception:
        return None


__all__ = ["router"]
