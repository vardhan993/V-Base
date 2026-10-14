# Backend architecture

## Runtime

- Python 3.12+
- FastAPI + Uvicorn (ASGI)
- **PostgreSQL** via SQLAlchemy 2.0 async + `asyncpg`
- Alembic for migrations (the only supported way to change the schema)
- Argon2 for password hashing
- pandas + openpyxl for spreadsheet import
- orjson for JSON responses, structured JSON logs on stdout

There is no SQLite fallback anywhere. `DATABASE_URL` is validated at startup and
a non-PostgreSQL DSN aborts the process with a clear message.

## Directory layout

```
backend/
  alembic/versions/         migration scripts (single head: 0001_initial)
  src/nexus/
    app.py                  FastAPI app factory, middleware chain, health probes
    api/v1/                 routers: auth, companies, contacts, leads, tasks, lists,
                            tags, search, views, custom fields, import, duplicates,
                            quality, analytics, activity, email, sequences,
                            settings, users
    commands/               operator CLI: run, migrate, admin, backup
    core/                   config, db engine, security, middleware, logging, audit,
                            email (Resend/Gmail), sequences (dispatch loop)
    database/               SQLAlchemy models and the session/Base wiring
    schemas/                Pydantic request/response models
  tests/                    pytest suite (runs against a real PostgreSQL database)
```

## Configuration

All configuration is environment-driven; see
[`backend/.env.example`](../backend/.env.example).

- `DATABASE_URL` — `postgresql+asyncpg://…`. Query parameters from the provider's
  connection string (`sslmode=require`, `channel_binding=…`) are translated into
  what `asyncpg` accepts, or dropped with a warning, rather than raising a
  `TypeError` deep in the driver.
- `SECRET_KEY` — sessions and CSRF tokens. `validate_production()` refuses to boot
  with `ENVIRONMENT=production` while this is the placeholder.
- `FRONTEND_URL` / `EXTRA_ALLOWED_ORIGINS` — the CORS and CSRF origin allow-list.

## Data access

- One async engine per process, created lazily, disposed on shutdown.
- `pool_pre_ping=True` and a `pool_recycle` below the provider's idle timeout: on
  Neon, a suspended compute wakes on the next connection and dead sockets are
  replaced transparently.
- Prepared-statement caching is disabled automatically when the DSN points at a
  PgBouncer transaction pooler (a `-pooler` hostname or port 6543).
- Every query uses bound parameters. No string interpolation of user input.
- The browser never receives the DSN and cannot reach PostgreSQL.

## Migrations

```bash
python -m nexus.commands.migrate upgrade      # apply to head
python -m nexus.commands.migrate current
python -m nexus.commands.migrate check        # detect model/migration drift
```

The initial migration enables `pg_trgm` before building the trigram GIN indexes,
and `search_vector` generated columns are maintained by PostgreSQL itself.

## Search

- `pg_trgm` GIN indexes on `lower(name)` and `lower(domain)` — verified to be used
  by the planner (Bitmap Index Scan) rather than falling back to a sequential scan.
- `tsvector` generated columns with GIN indexes for full-text search across
  companies and contacts.
- Server-side pagination, sorting and nested AND/OR filter groups are applied in
  SQL; the API never loads a table to filter it in Python.

## Requests, safety and observability

Middleware runs, outermost first:

1. `RequestContextMiddleware` — assigns a request id, emits one structured access
   log line per request with method, path, status, duration and user id.
2. `CsrfOriginMiddleware` — rejects unsafe cross-site requests (Origin/Referer must
   be allow-listed) and enforces a double-submit CSRF token whenever a session
   cookie is present.
3. `RateLimitMiddleware` — per-client sliding window: a tight bucket for `/auth/*`
   and a broader one for writes. State is per process, which matches the
   single-instance free tier.
4. `SecurityHeadersMiddleware` — `X-Content-Type-Options`, `X-Frame-Options`,
   `Referrer-Policy`, and HSTS in production.
5. CORS with credentials, restricted to the configured origins.
6. GZip for responses above 1 KiB.

Uploads are validated by extension, size, and file signature (`PK\x03\x04` for
`.xlsx`, the OLE magic for `.xls`, a binary-content check for `.csv`), stored under
a UUID filename, and read back only through a path-traversal guard that confines
access to the uploads directory.

## Health probes

| Endpoint | Meaning |
|---|---|
| `GET /health` | Liveness only — the process is up. No database round trip. |
| `GET /health/ready` | Readiness — executes `SELECT 1` and reports pool stats. `503` when PostgreSQL is unreachable. |

`init_db()` additionally asserts that a schema revision exists, so the API refuses
to serve against an unmigrated or empty database.

## Imports

Every row is planned before anything is written, and the run happens in a single
transaction — a failure rolls back completely, so a partial import is impossible.
`fill_empty` never overwrites a populated column; `overwrite` records each replaced
value in the per-row report and the audit log. See
[BACKUP.md](BACKUP.md) for the recovery side and the Import Center page for the
wizard.

## Operator CLI

```bash
python -m nexus.commands.run              # uvicorn with parsed flags
python -m nexus.commands.migrate ...      # schema management
python -m nexus.commands.admin ...        # create-admin, promote, stats, cleanup-sessions
python -m nexus.commands.backup ...       # create, list, verify, restore
```

Installed console scripts (`vbase-run`, `vbase-migrate`, `vbase-admin`,
`vbase-backup`) come from `pip install -e backend`.
