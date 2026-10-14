"""Locate the PostgreSQL client binaries (``pg_dump`` / ``pg_restore``).

A container or managed host usually ships them on ``PATH``. A Windows
developer install, however, drops them under
``C:\\Program Files\\PostgreSQL\\<major>\\bin`` and never touches ``PATH`` -
which is why Backup & Restore reported "pg_dump: Not installed" and silently
fell back to JSON snapshots even though the binary was sitting on disk.

Resolution order for each tool:

1. an explicit path configured with ``PG_DUMP_PATH`` / ``PG_RESTORE_PATH``
   (the default value is the bare command name, which just means "use PATH");
2. ``shutil.which`` - the normal lookup, honouring ``PATHEXT`` on Windows;
3. the well-known install directories, newest PostgreSQL major first.

Nothing here executes the binaries; :mod:`nexus.api.v1.settings` owns that.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

#: Roots that hold per-version sub-directories (``<root>/<major>/bin``).
_VERSIONED_ROOTS = (
    r"C:\Program Files\PostgreSQL",
    r"C:\Program Files (x86)\PostgreSQL",
    r"C:\PostgreSQL",
    "/usr/lib/postgresql",
    "/opt/local/lib/postgresql",
    "/Library/PostgreSQL",
    "/Applications/Postgres.app/Contents/Versions",
)

#: Roots whose ``bin`` directory sits directly underneath (``<root>/bin``).
_DIRECT_ROOTS = (
    "/usr/local/pgsql",
    "/usr/local",
    "/opt/homebrew",
    "/opt/homebrew/opt/postgresql",
)


def _version_key(name: str) -> tuple[int, ...]:
    """Sort key that puts ``18`` above ``9.6`` above ``psqlODBC``."""
    numbers = tuple(int(part) for part in re.findall(r"\d+", name))
    return numbers or (0,)


def _search_dirs() -> list[Path]:
    """Candidate directories that may hold the client binaries, best first."""
    dirs: list[Path] = []
    for root in _VERSIONED_ROOTS:
        base = Path(root)
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir(), key=lambda p: _version_key(p.name), reverse=True)
        except OSError:  # pragma: no cover - unreadable install dir
            continue
        for child in children:
            if child.is_dir():
                dirs.append(child / "bin")
    for root in _DIRECT_ROOTS:
        dirs.append(Path(root) / "bin")
    return dirs


def _executable_name(tool: str) -> str:
    return f"{tool}.exe" if sys.platform == "win32" else tool


@lru_cache(maxsize=16)
def resolve_pg_binary(tool: str, configured: str | None = None) -> str | None:
    """Absolute path to ``tool``, or None when it cannot be found.

    ``configured`` is the value from settings. An absolute path there is used
    only if it exists; a bare name (the default) is looked up on ``PATH``.
    """
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate)

    found = shutil.which(configured or tool)
    if found:
        return found

    exe = _executable_name(tool)
    for directory in _search_dirs():
        candidate = directory / exe
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        except OSError:  # pragma: no cover - permission denied on stat
            continue
    return None


def pg_client_env(binary: str, *, password: str | None, sslmode: str | None) -> dict[str, str]:
    """Minimal, portable environment for a ``pg_dump``/``pg_restore`` child.

    The previous implementation hard-coded a POSIX ``PATH`` and forwarded
    nothing else, so on Windows the child could not load ``libpq.dll`` (it
    lives beside the executable) and failed even when the binary was found.
    Only the binary's own directory plus the loader essentials are forwarded -
    the rest of the parent environment is deliberately not inherited.
    """
    binary_dir = str(Path(binary).parent)
    env: dict[str, str] = {
        "PATH": os.pathsep.join(filter(None, (binary_dir, os.environ.get("PATH", "")))),
        "PGPASSWORD": password or "",
        # ``prefer`` negotiates TLS and still works against a local server that
        # has SSL disabled, which ``require`` did not.
        "PGSSLMODE": sslmode or "prefer",
    }
    for key in ("SystemRoot", "windir", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env
