# V-Base

### Your Business Data. One Powerful Base.

A complete B2B company and professional-contact intelligence platform. Import
spreadsheets of technology companies, founders, CEOs, CTOs, HR leaders and
recruiters, then clean, deduplicate, segment and analyse them in one place.

Everything runs on free tiers with no paid APIs and no automatic billing:
PostgreSQL for the data, FastAPI for the API, and a React SPA on the edge.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, TypeScript, Tailwind CSS, Radix UI, Lucide, Recharts, Zustand |
| Backend | Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2 (async), Pydantic v2, pandas, openpyxl |
| Database | **PostgreSQL** via `asyncpg`, Alembic migrations, `pg_trgm` + `tsvector` search indexes |
| Auth | Argon2 password hashing, server-side sessions in an HttpOnly cookie, CSRF double-submit |
| Hosting | Frontend on Cloudflare Workers Static Assets, API on Render (free), database on Neon (free) |

Three independent components, connected only through an environment-configured
API origin and a database DSN. The browser never talks to PostgreSQL, and no
credential ever reaches the client bundle.

---

## Features

**Data** — companies and contacts with full CRUD, detailed profiles, inline
editing, bulk actions, configurable columns, server-side pagination/sorting,
nested AND/OR filters, saved views and saved searches.

**Search** — global search plus a Ctrl/⌘-K command palette, backed by `pg_trgm`
trigram indexes for fuzzy matching and `tsvector` generated columns for full-text
search. Both are verified to use their indexes.

**Import Center** — a six-step wizard for CSV/XLSX: signature-validated upload,
worksheet selection, row preview, automatic and manual column mapping, import
strategy (add / update / add-and-update / skip duplicates), update policy
(fill-blanks-only or overwrite), a **dry run** that shows the exact field-level
diff per row, live progress during the run, and downloadable CSV/XLSX reports
plus an error report. A failed import rolls back completely.

**Duplicates** — candidate detection, side-by-side comparison, safe merge,
keep-both, dismiss and reopen, with an audit trail.

**Data quality** — completeness scoring, needs-review queues, and a
configurable weighting of what "complete" means.

**Organisation** — reusable tags with bulk apply/remove, contact and company
lists, custom fields (text, number, date, select, multi-select, boolean …) with
typed values per record.

**Operations** — activity and audit logs, users and roles, active-session
management, application settings, and PostgreSQL backup/restore with real artifact
validation, a safety snapshot before every restore, and a documented recovery
playbook.

---

## Quick start (Windows)

```bat
install.bat          :: venv + backend + frontend + .env files
postgres.bat         :: local PostgreSQL 16 on port 5433 (Docker)
migrate.bat          :: alembic upgrade head
start.bat            :: API on :8000 + SPA on :5173
```

Then open <http://localhost:5173>, create an account, and promote it to
administrator so the Users and Restore features unlock:

```bat
.venv\Scripts\python.exe -m nexus.commands.admin create-admin --email you@example.com --username you
.venv\Scripts\python.exe -m nexus.commands.admin promote --email you@example.com
```

`stop.bat` shuts down the processes start.bat launched; `postgres.bat stop` stops
the database container while keeping its data.

### Quick start (macOS / Linux / manual)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]"

cp backend/.env.example backend/.env     # then edit DATABASE_URL and SECRET_KEY
cp apps/web/.env.example apps/web/.env

# any PostgreSQL 14+ instance; pg_trgm is created by the migration
python -m nexus.commands.migrate upgrade
python -m nexus.commands.run --reload          # API on :8000

cd apps/web && npm install && npm run dev      # SPA on :5173
```

### Prerequisites

- Python **3.12+**
- Node.js **20+** and npm
- PostgreSQL **14+** — either Docker (for the bundled dev container) or your own
  instance. SQLite is **not** supported and the API refuses a non-PostgreSQL DSN.

---

## Configuration

Copy the templates; never commit the results.

| File | Purpose |
|---|---|
| [`backend/.env.example`](backend/.env.example) | API: `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL`, pool and limit tuning |
| [`apps/web/.env.example`](apps/web/.env.example) | SPA: `VITE_API_BASE` (blank uses the Vite proxy in development) |
| [`.env.example`](.env.example) | Index of the above and what must never be committed |

Required for any deployment:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` — the pooled connection string from Neon/Tiger Cloud |
| `SECRET_KEY` | 32+ random characters: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `FRONTEND_URL` | The exact browser origin allowed to call the API (no trailing slash) |
| `VITE_API_BASE` | API origin baked into the frontend build, e.g. `https://vbase-api.onrender.com/api/v1` |

With `ENVIRONMENT=production` the API refuses to start while `SECRET_KEY` is the
placeholder or `DATABASE_URL` still points at the local development database, and
it forces the session cookie to `Secure`.

---

## Project structure

```
apps/web/                 React SPA (Vite) — wrangler.jsonc deploys dist/ to Cloudflare
backend/
  alembic/versions/       migrations (single head: 0001_initial)
  src/nexus/
    api/v1/               REST routers under /api/v1
    core/                 config, engine, middleware, security, logging, audit
    database/             SQLAlchemy models
    schemas/              Pydantic models
    commands/             operator CLI: run, migrate, admin, backup
  Dockerfile              production image (includes postgresql-client)
  .env.example            configuration template
tests/backend/            pytest suite, runs against a real PostgreSQL database
scripts/windows/          PowerShell launchers + .bat wrappers
docs/                     DEPLOYMENT.md, BACKUP.md, CLOUDFLARE.md, architecture/
render.yaml               Render blueprint for the free API service
docker-compose.yml        local PostgreSQL + API stack
```

---

## Database

A normalised PostgreSQL schema with foreign keys, constraints, indexes and
timestamps across: `users`, `sessions`, `companies`, `contacts`,
`contact_emails`, `contact_phones`, `employment_history`, `lists`,
`list_contacts`, `list_companies`, `tags`, `contact_tags`, `company_tags`,
`saved_searches`, `saved_views`, `import_jobs`, `import_rows`, `import_errors`,
`duplicate_candidates`, `verification_events`, `activity_logs`, `audit_logs`,
`custom_fields`, `custom_field_values`, `settings`.

Search is served by `pg_trgm` GIN indexes on `lower(name)`/`lower(domain)` and by
`tsvector` generated columns with GIN indexes on companies and contacts. The
initial migration enables the extension itself.

Migrations:

```bash
python -m nexus.commands.migrate upgrade     # apply to head
python -m nexus.commands.migrate current     # applied revision
python -m nexus.commands.migrate check       # detect model/migration drift
```

---

## Testing and builds

```bash
# Backend: 116 tests against a real PostgreSQL database (not mocks)
python -m pytest

# Frontend: type check + production build
cd apps/web
npm run type-check
npm run build

# Cloudflare config sanity check (no upload)
cd apps/web && npx wrangler deploy --dry-run
```

The backend suite expects the same database the app uses; start the dev container
and migrate first. It exercises auth and sessions, CRUD and filters, search,
imports (including the plan/dry-run path), tags, lists, duplicates, quality,
analytics, settings, backup/restore round-trips, and the security middleware.

---

## Security

- Passwords hashed with Argon2; never stored or logged in plain text.
- Session tokens are stored server-side as SHA-256 hashes, so a database dump
  yields no usable cookie. Cookies are HttpOnly, `SameSite=Lax`, and `Secure` in
  production.
- CSRF double-submit token on every unsafe request, plus an exact Origin
  allow-list that rejects cross-site mutations with `403`.
- Per-IP sliding-window rate limiting on auth and write traffic.
- Security headers, HSTS in production, GZip, and structured JSON request logs.
- Uploads validated by extension, size and file signature, stored under generated
  names, and read back only inside the uploads directory.
- Every query uses bound parameters; SQLAlchemy sessions are transaction-scoped.
- Imported business data is private by default: every route requires a session.
- An email or phone is never labelled "verified" unless a real verification event
  recorded it — imported status fields are carried through as source data, not
  presented as V-Base's own confirmation.

---

## Deployment

Full instructions with verified free-tier limits and sources:
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

- **Database** — [Neon](https://neon.com) serverless PostgreSQL: 1 GB per project,
  no credit card, no expiry, `pg_trgm` supported. Compute suspends after ~5 minutes
  idle and wakes on the next connection. (Tiger Cloud's free plan, 750 MB with no
  card, is a documented alternative.)
- **API** — [Render](https://render.com) free Python web service: free managed TLS,
  HTTP health checks, 750 instance-hours per month, no card and no automatic
  upgrade. Free instances sleep after 15 minutes of inactivity (~1 minute cold
  start).
- **Frontend** — Cloudflare Workers Static Assets (assets-only config, SPA
  fallback). Cloudflare's Python runtime cannot host this backend: async SQLAlchemy
  is unsupported there (no `greenlet`) and the pandas/openpyxl import stack is not
  available as WebAssembly wheels — see [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

Backups, restores and disaster recovery: **[docs/BACKUP.md](docs/BACKUP.md)**.

---

## Limitations

Stated plainly so nothing is oversold:

- **No deployment is included in this repository.** The configuration for all
  three hosts is complete and validated locally (`wrangler deploy --dry-run`
  passes), but publishing requires your accounts and credentials.
- Origin verification is done by API integration tests plus a local end-to-end
  run, not by a cloud smoke test against a live Render/Neon deployment.
- Rate limiting is per process. On a single free instance that is a real limit; on
  multiple instances it becomes a per-instance ceiling.
- Uploaded source spreadsheets live on the API host's filesystem, which is
  ephemeral on free hosting. Keep your originals.
- Backup files written on free hosting are ephemeral too — download the export, or
  use the database provider's point-in-time restore.
- Email and phone verification is not implemented. V-Base records verification
  status from your source data and never claims to have verified a contact itself.
- Single-tenant workspace: authentication gates the whole API, but records are not
  partitioned per user.
- The largest frontend bundle is ~1.7 MB uncompressed; route-level code splitting
  is not enabled yet.

---

## License

Free and open source. No paid services, no paid APIs, no automatic upgrades.
