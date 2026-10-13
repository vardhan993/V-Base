"""Backup and restore from the command line.

Usage::

    python -m nexus.commands.backup create
    python -m nexus.commands.backup list
    python -m nexus.commands.backup verify backups/vbase_snapshot_20261013_090000.json
    python -m nexus.commands.backup restore backups/vbase_snapshot_20261013_090000.json

The heavy lifting lives in ``nexus.api.v1.settings`` so the CLI and the HTTP
API can never drift apart: both read every table through ``SNAPSHOT_TABLES``
and both validate an artifact before trusting it. A ``pg_dump`` custom-format
archive is never replayed in-process - the CLI prints the ``pg_restore``
command instead, so an operator stays in control of a destructive step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from nexus.core.config import settings

logger = logging.getLogger("vbase.backup")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vbase-backup",
        description=f"{settings.app_name} - PostgreSQL backup and restore",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a backup (pg_dump when available, else a JSON snapshot)")
    create.add_argument("--json", action="store_true", help="Force a portable JSON snapshot")

    sub.add_parser("list", help="List backups in the backup directory with validation results")

    verify = sub.add_parser("verify", help="Validate a backup artifact without restoring it")
    verify.add_argument("file")

    restore = sub.add_parser("restore", help="Restore a JSON snapshot, or print the pg_restore command for a dump")
    restore.add_argument("file")
    restore.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (required for non-interactive use)",
    )
    return parser


def _resolve(path_str: str) -> Path:
    """Only allow files inside the configured backup directory."""
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = settings.backups_path / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(settings.backups_path.resolve())
    except ValueError:
        raise SystemExit(f"Refusing to touch {resolved}: outside {settings.backups_path}") from None
    if not resolved.is_file():
        raise SystemExit(f"No such backup file: {resolved}")
    return resolved


def _pg_restore_hint(path: Path) -> str:
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    return (
        f"pg_restore --clean --if-exists --no-owner "
        f"--host={host} --port={port} --username={url.username} --dbname={url.database} {path}"
    )


async def _create(force_json: bool) -> int:
    from nexus.api.v1.settings import _export_snapshot, _pg_dump_available, _run_pg_dump, _stamp, _validate_backup
    from nexus.core.db import session_scope

    settings.backups_path.mkdir(parents=True, exist_ok=True)
    # Import-time import of Base keeps the snapshot table order identical to the API.
    from nexus.database import Base  # noqa: F401  (ensures models are registered)

    kind = "json"
    name = f"vbase_snapshot_{_stamp()}.json"
    dest = settings.backups_path / name

    if not force_json and _pg_dump_available():
        name = f"vbase_dump_{_stamp()}.sql"
        dest = settings.backups_path / name
        try:
            _run_pg_dump(dest)
            kind = "pg_dump"
        except Exception as exc:  # noqa: BLE001 - fall back deliberately
            logger.warning("pg_dump failed (%s); writing a JSON snapshot instead", exc)
            name = f"vbase_snapshot_{_stamp()}.json"
            dest = settings.backups_path / name
            kind = "json"

    if kind == "json":
        async with session_scope() as session:
            payload = await _export_snapshot(session)
        dest.write_text(json.dumps(payload), encoding="utf-8")

    validation = _validate_backup(dest, kind)
    if not validation.get("valid"):
        dest.unlink(missing_ok=True)
        print(f"FAILED validation: {validation.get('error')}", file=sys.stderr)
        return 1

    print(f"Created {kind} backup: {dest}")
    print(f"  size: {dest.stat().st_size} bytes")
    print(f"  validation: {validation}")
    return 0


def _list() -> int:
    from nexus.api.v1.settings import _validate_backup

    directory = settings.backups_path
    directory.mkdir(parents=True, exist_ok=True)
    files = sorted([*directory.glob("*.json"), *directory.glob("*.sql")], key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"No backups in {directory}")
        return 0

    print(f"Backups in {directory}:")
    for path in files:
        kind = "pg_dump" if path.suffix == ".sql" else "json"
        validation = _validate_backup(path, kind)
        status = "valid" if validation.get("valid") else f"INVALID ({validation.get('error')})"
        print(f"  {path.name:52s} {path.stat().st_size:>12,} B  {kind:8s} {status}")
    return 0


def _verify(path: Path) -> int:
    from nexus.api.v1.settings import _validate_backup

    kind = "pg_dump" if path.suffix == ".sql" else "json"
    validation = _validate_backup(path, kind)
    print(json.dumps({"file": str(path), "kind": kind, "validation": validation}, indent=2))
    return 0 if validation.get("valid") else 1


async def _restore(path: Path, assume_yes: bool) -> int:
    from nexus.api.v1.settings import _export_snapshot, _restore_snapshot, _stamp, _validate_backup
    from nexus.core.db import session_scope

    kind = "pg_dump" if path.suffix == ".sql" else "json"
    validation = _validate_backup(path, kind)
    if not validation.get("valid"):
        print(f"FAILED validation: {validation.get('error')}", file=sys.stderr)
        return 1

    if kind == "pg_dump":
        print("This is a physical pg_dump archive. V-Base will not replay it in-process.")
        print("Run this deliberately, against a database you are prepared to overwrite:")
        print()
        print("  " + _pg_restore_hint(path))
        print()
        print("Then re-apply migrations to confirm the schema revision:")
        print("  python -m nexus.commands.migrate upgrade")
        return 0

    if not assume_yes:
        answer = input(f"Restore {path.name} over the live database? Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            return 1

    # A safety snapshot is always written before anything is replaced.
    async with session_scope() as session:
        safety = settings.backups_path / f"pre_restore_{_stamp()}.json"
        safety.write_text(json.dumps(await _export_snapshot(session)), encoding="utf-8")
        payload = json.loads(path.read_text(encoding="utf-8"))
        restored = await _restore_snapshot(session, payload)

    print(f"Restored {restored} row(s) from {path.name}")
    print(f"Safety snapshot written to {safety}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "create":
        return asyncio.run(_create(bool(getattr(args, "json", False))))
    if args.command == "list":
        return _list()
    if args.command == "verify":
        return _verify(_resolve(args.file))
    if args.command == "restore":
        return asyncio.run(_restore(_resolve(args.file), bool(args.yes)))
    return 2  # pragma: no cover - argparse enforces the choice


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
