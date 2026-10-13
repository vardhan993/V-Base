"""Alembic wrapper used by scripts, CI and the hosting provider's start command.

Deliberately small: it locates ``alembic.ini`` next to the package root so the
command works no matter what the current working directory is.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from nexus.core.config import settings

logger = logging.getLogger("vbase.migrate")

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config():
    from alembic.config import Config

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vbase-migrate", description="Manage the V-Base PostgreSQL schema")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("upgrade", help="Apply all pending migrations (alembic upgrade head)")
    sub.add_parser("current", help="Show the revision the database is on")
    sub.add_parser("history", help="List migration revisions")
    sub.add_parser("check", help="Fail if models and migrations have drifted apart")

    revision = sub.add_parser("revision", help="Create a new migration")
    revision.add_argument("-m", "--message", required=True)
    revision.add_argument("--autogenerate", action="store_true")

    downgrade = sub.add_parser("downgrade", help="Roll back one revision")
    downgrade.add_argument("revision", nargs="?", default="-1")

    stamp = sub.add_parser("stamp", help="Mark the database as being at a revision without running it")
    stamp.add_argument("revision", nargs="?", default="head")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from alembic import command

    config = _alembic_config()
    logger.info("Using %s", settings.database_url.split("@")[-1])

    if args.command == "upgrade":
        command.upgrade(config, "head")
    elif args.command == "downgrade":
        command.downgrade(config, args.revision)
    elif args.command == "revision":
        command.revision(config, message=args.message, autogenerate=args.autogenerate)
    elif args.command == "current":
        command.current(config)
    elif args.command == "history":
        command.history(config)
    elif args.command == "check":
        command.check(config)
    elif args.command == "stamp":
        command.stamp(config, args.revision)
    else:  # pragma: no cover - argparse enforces the choice
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
