# V-Base API — production image.
#
# Built from the backend/ directory:
#   docker build -t vbase-api ./backend
#
# Debian slim is used rather than alpine so the official PostgreSQL client
# binaries (pg_dump / pg_restore) come from a maintained package and asyncpg
# gets a prebuilt wheel instead of compiling against musl.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# postgresql-client provides pg_dump/pg_restore, which the backup feature uses
# when present. Without them the API falls back to validated JSON snapshots.
RUN apt-get update \
 && apt-get install --no-install-recommends -y postgresql-client curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first so application edits do not invalidate the pip cache.
COPY pyproject.toml README.md ./
COPY src ./src
# Runtime dependencies only — the dev extras (pytest, ruff) belong in the
# developer venv and CI, not in a production image.
RUN pip install --upgrade pip setuptools wheel \
 && pip install .

COPY alembic.ini ./

# Migrations ship inside the nexus package (src/nexus/migrations); see
# nexus.commands.migrate, which resolves the script location from the
# installed package so no filesystem layout is assumed.

# Run as an unprivileged user; the app never needs to write outside its
# configured uploads/backups directories.
RUN useradd --create-home --uid 10001 vbase \
 && mkdir -p /app/uploads /app/backups \
 && chown -R vbase:vbase /app
USER vbase

ENV PYTHONPATH=/app/src \
    ENVIRONMENT=production \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    UPLOADS_DIR=/app/uploads \
    BACKUPS_DIR=/app/backups

EXPOSE 8000

# /health is a pure liveness probe (no database round trip), which is what a
# container runtime should check before routing traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Migrations run at start-up so a fresh database is always migrated to head
# before the API serves traffic. The wrapper fails loudly if the database is
# unreachable, which stops a broken deploy from receiving requests.
CMD ["sh", "-c", "python -m nexus.commands.migrate upgrade && exec uvicorn nexus.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
