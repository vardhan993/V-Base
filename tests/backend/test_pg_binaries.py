"""PostgreSQL client binary discovery and child-process environment."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from nexus.core.pg_binaries import pg_client_env, resolve_pg_binary


def test_resolve_prefers_an_explicit_existing_path():
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / ("pg_dump.exe" if os.name == "nt" else "pg_dump")
        candidate.write_text("#!/bin/sh\n", encoding="utf-8")
        candidate.chmod(0o755)

        assert resolve_pg_binary("vbase_fake_tool_a", str(candidate)) == str(candidate)


def test_resolve_ignores_a_missing_override_and_falls_through():
    # An unset/missing path must not be returned as if it were a real binary.
    assert resolve_pg_binary("vbase_fake_tool_b", "/definitely/not/here/pg_dump") is None


def test_resolve_returns_none_for_an_unknown_tool():
    assert resolve_pg_binary("vbase_definitely_not_a_tool_c") is None


def test_resolve_finds_a_binary_that_is_on_path():
    # ``python`` (or ``python.exe``) is on PATH in every environment that runs
    # this suite, so the PATH branch is exercised without a real pg_dump.
    tool = "python" if shutil.which("python") else "python3"
    resolved = resolve_pg_binary(tool)
    assert resolved is not None
    assert Path(resolved).name.startswith(tool)


def test_client_env_is_portable_and_minimal():
    binary = str(Path(tempfile.gettempdir()) / "pg_bin" / "pg_dump")
    env = pg_client_env(binary, password="secret", sslmode=None)

    # The binary's own directory leads PATH so libpq can be loaded beside it.
    assert env["PATH"].split(os.pathsep)[0] == str(Path(binary).parent)
    assert env["PGPASSWORD"] == "secret"
    # Local servers without TLS still work; managed hosts negotiate it.
    assert env["PGSSLMODE"] == "prefer"
    # Nothing unrelated from the parent environment leaks into the child.
    assert "HOME" not in env


def test_client_env_honours_an_explicit_sslmode():
    env = pg_client_env("pg_dump", password=None, sslmode="require")
    assert env["PGSSLMODE"] == "require"
    assert env["PGPASSWORD"] == ""
