"""Alembic wrapper used by scripts, CI and the hosting provider's start command.

Deliberately small: the migrations live inside the ``nexus`` package
(``nexus/migrations``) so they are shipped with the wheel. The script
location is therefore resolved from the installed package rather than the
source checkout, which keeps the command working both in development and in
a deployed pip-installed environment with no filesystem assumptions.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from nexus.core.config import settings

logger = logging.getLogger("vbase.migrate")

#: ``nexus/commands/migrate.py`` -> ``nexus/migrations`` (works in a source
#: checkout and inside site-packages alike).
SCRIPT_LOCATION = Path(__file__).resolve().parents[1] / "migrations"


def _alembic_config():
    from alembic.config import Config

    ini = Path.cwd() / "alembic.ini"  # used only for its logging section
    if ini.is_file():
        config = Config(str(ini))
    else:
        config = Config()
        config.config_file_name = None
        # Match the logging section of alembic.ini so output is not swallowed.
        import logging.config

        logging.config.dictConfig({
            "version": 1,
            "disable_existing_loggers": False,
            "loggers": {
                "alembic": {"level": "INFO", "handlers": []},
                "sqlalchemy": {"level": "WARNING", "handlers": []},
                "": {"level": "INFO", "handlers": ["console"], "propagate": False},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "generic",
                    "stream": "ext://sys.stderr",
                },
            },
            "formatters": {"generic": {"format": "%(levelname)-5.5s [%(name)s] %(message)s"}},
        })
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
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
