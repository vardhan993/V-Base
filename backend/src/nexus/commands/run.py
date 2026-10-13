from __future__ import annotations

import argparse
import logging
import sys

from nexus.core.config import settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vbase",
        description=f"{settings.app_name} API server - {settings.tagline}",
    )
    parser.add_argument("--host", default=settings.backend_host, help="Bind address (default: %(default)s)")
    parser.add_argument("--port", type=int, default=settings.backend_port, help="Bind port (default: %(default)s)")
    parser.add_argument("--reload", action="store_true", help="Restart on source changes (development only)")
    parser.add_argument("--workers", type=int, default=1, help="Worker processes (default: %(default)s)")
    parser.add_argument(
        "--log-level", default="info", choices=["critical", "error", "warning", "info", "debug", "trace"]
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import uvicorn

    uvicorn.run(
        "nexus.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
