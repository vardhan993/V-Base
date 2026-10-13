# Deploying V-Base

V-Base is three independent components that talk over HTTPS and a database DSN:

| Component | Runs on | Free tier used | Talks to |
|---|---|---|---|
| Frontend (React + Vite SPA) | **Cloudflare Workers Static Assets** | Workers free plan | Backend API over HTTPS |
| Backend (FastAPI + SQLAlchemy) | **Render** free web service (Python) | 750 instance-hours/month | PostgreSQL over TLS |
| Database | **Neon** serverless PostgreSQL | 1 GB/project, no expiry | — |

Nothing in this setup requires a credit card or creates a paid resource. The
browser never connects to PostgreSQL: only the API holds the DSN.

Order matters — create the database first, then the API, then point the frontend
at it.

---

## 0. Why not Cloudflare Workers for the backend

The brief asked for the backend to go on Cloudflare only if the Python runtime
and every required dependency are genuinely compatible. They are not, and
Cloudflare's own documentation says so:

* Python Workers execute CPython compiled to WebAssembly (Pyodide) inside a V8
  isolate — not a long-lived Python server.
* Cloudflare's Hyperdrive Python guide states that **only synchronous SQLAlchemy
  ORMs are supported** and that async SQLAlchemy is not available because the
  runtime lacks `greenlet`. V-Base's data layer is async SQLAlchemy + `asyncpg`.
* Package support is limited to pure-Python and PyEmscripten-compatible wheels;
  the `pandas` + `openpyxl` import pipeline is not guaranteed to build.

Sources: [How Python Workers work](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/),
[Python packages supported in Workers](https://developers.cloudflare.com/workers/languages/python/packages/),
[Python Workers · Hyperdrive](https://developers.cloudflare.com/hyperdrive/examples/python-workers/).

So the backend runs on a real Python host (Render, below), and Cloudflare is used
for exactly what it does best here: serving the static SPA at the edge.

---

## 1. Database — Neon serverless PostgreSQL (free)

### Verified free-plan facts

Checked against Neon's own documentation at the time of writing:

| Property | Free plan |
|---|---|
| Storage | 1 GB per project, 20 GB per account |
| Compute | 100 CU-hours per project per month (≈400 active hours at the 0.25 CU default) |
| Projects / branches | 100 projects, 10 branches per project |
| Credit card | **Not required** |
| Expiry | **None** — the plan has no time limit |
| Idle behaviour | Compute suspends after ~5 minutes idle (scale-to-zero); the next connection wakes it in a few hundred milliseconds |
| Connections | Pooled via PgBouncer (hostname contains `-pooler`); underlying `max_connections` ≈97 at 0.25 CU |
| `pg_trgm` | Available (`CREATE EXTENSION IF NOT EXISTS pg_trgm`) — used by V-Base's fuzzy-match indexes |
| Backups | Short point-in-time restore window on Free; branch/fork from the console |

Sources: [Neon pricing](https://neon.com/pricing), [Plans](https://neon.com/docs/introduction/plans),
[Scale to zero](https://neon.com/docs/guides/scale-to-zero-guide), [Connection pooling](https://neon.com/docs/connect/connection-pooling),
[pg_trgm](https://neon.com/docs/extensions/pg_trgm).

> **Alternative if you prefer a non-serverless host:** Tiger Cloud's free plan
> gives 2 services of 750 MB with no credit card and no time limit, and is also
> plain PostgreSQL with `pg_trgm`. Its connection string works with the same DSN
> translation V-Base already performs.

### Create the database

1. Sign up at <https://neon.com> (no card is requested on the Free plan).
2. Create a project. Pick the region closest to your Render region (`oregon` in
   the blueprint below → `aws-us-west-2`).
3. On the project dashboard, open **Connection string** and choose the
   **Pooled connection** variant. It looks like:

   ```
   postgresql://USER:PASSWORD@ep-xxx-pooler.us-west-2.aws.neon.tech/vbase?sslmode=require
   ```

4. Rewrite the driver prefix for SQLAlchemy's async engine:

   ```
   postgresql+asyncpg://USER:PASSWORD@ep-xxx-pooler.us-west-2.aws.neon.tech/vbase?sslmode=require
   ```

   Keep the `-pooler` hostname. V-Base detects it and disables asyncpg's
   prepared-statement cache automatically, which would otherwise break behind a
   transaction pooler.

You do **not** need to create the schema by hand — the first API deploy runs
`alembic upgrade head`. If you prefer to do it now, see
[Applying migrations](#4-applying-migrations).

---

## 2. Backend — Render free web service (Python)

Cloudflare Workers cannot run this stack (§0), so the API runs on Render, which
offers a genuine free Python web service with no card requirement.

### Verified free-instance facts

| Property | Render Free |
|---|---|
| Python web services | Supported (FastAPI/Uvicorn included) |
| Sleep | Spins down after **15 minutes** without inbound traffic |
| Cold start | About **1 minute** on the next request |
| Runtime allowance | **750 instance-hours** per workspace per calendar month, shared across free services |
| HTTPS | Free managed TLS with automatic HTTP → HTTPS redirect |
| Health checks | Configurable, including HTTP checks against a path |
| Credit card | **Not required**; no automatic upgrade to a paid plan |

Sources: [Deploy for Free](https://render.com/docs/free), [Web Services](https://render.com/docs/web-services),
[Health Checks](https://render.com/docs/health-checks), [TLS](https://render.com/docs/tls).

### Deploy

1. Push this repository to GitHub/GitLab.
2. Render dashboard → **New → Blueprint** → select the repository. Render reads
   [`render.yaml`](../render.yaml) and creates the `vbase-api` service.
3. Render prompts for the values marked `sync: false` in the blueprint:
   * `DATABASE_URL` — the `postgresql+asyncpg://…-pooler…?sslmode=require` string from §1
   * `SECRET_KEY` — generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   * `FRONTEND_URL` — the Workers URL from §3, e.g. `https://vbase.<subdomain>.workers.dev`
   * `EXTRA_ALLOWED_ORIGINS` — any custom domain, comma-separated (optional)
4. Deploy. The start command runs migrations and then Uvicorn:

   ```
   python -m nexus.commands.migrate upgrade && \
   uvicorn nexus.app:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
   ```

5. Verify:

   ```bash
   curl -s https://vbase-api.onrender.com/health          # liveness
   curl -s https://vbase-api.onrender.com/health/ready     # liveness + PostgreSQL
   ```

   `/health/ready` returns **503** unless PostgreSQL answers and a schema
   revision is present, so a green result genuinely proves the database link.

6. Create your administrator account. Registration creates a normal member, so
   promote the first account:

   ```bash
   # from the Render shell (or locally against the same DATABASE_URL)
   python -m nexus.commands.admin create-admin --email you@example.com --username you
   python -m nexus.commands.admin promote --email you@example.com
   ```

   Without a promoted account nobody can reach `/api/v1/users`, and backup
   restore (superuser-only) stays unavailable.

### Confirming the backend actually started

* Render's log shows `V-Base API started` with the environment and version.
* `/health/ready` reports `"database": {"status": "ok", "pool": {...}}`.
* The first request after 15 idle minutes takes ~1 minute — that is the free
  plan waking up, not a failure. A free uptime monitor hitting `/health` every
  few minutes keeps it warm within the 750-hour allowance.

---

## 3. Frontend — Cloudflare Workers Static Assets

The SPA is a static bundle; no server logic is deployed.

```bash
cd apps/web
cp .env.example .env

# Point the build at the Render API. This value is compiled into the bundle, so
# it must be set before building, not after deploying.
echo "VITE_API_BASE=https://vbase-api.onrender.com/api/v1" > .env

npm ci
npm run build          # produces dist/
npx wrangler deploy    # reads wrangler.jsonc and uploads dist/
```

[`apps/web/wrangler.jsonc`](../apps/web/wrangler.jsonc) is an assets-only
configuration: no Worker script, `not_found_handling:
"single-page-application"` so a hard refresh on a deep link renders the app, and
observability enabled. Validate it without deploying:

```bash
cd apps/web
npm run build
npx wrangler deploy --dry-run
```

Then set `FRONTEND_URL` in Render to the exact deployed origin (scheme included)
and redeploy the API. Origins must match exactly — the API rejects cross-origin
mutations with 403 by design.

**Do not** put the API base in a `VITE_` variable that contains a secret: every
`VITE_` value is inlined into the public JavaScript bundle.

---

## 4. Applying migrations

Alembic is the only supported way to change the schema; the application never
issues DDL at runtime. Both the Docker image and the Render start command run
migrations automatically, but you can run them deliberately:

```bash
# locally (venv + backend/.env pointing at the target database)
python -m nexus.commands.migrate upgrade      # apply everything
python -m nexus.commands.migrate current      # which revision is applied
python -m nexus.commands.migrate check        # models vs migrations drift
python -m nexus.commands.migrate revision -m "add x" --autogenerate
```

The initial migration (`0001_initial`) enables `pg_trgm` itself, so a fresh Neon
database needs nothing beforehand.

---

## 5. Environment variables

| Where | File / place | Required keys |
|---|---|---|
| Backend (local) | `backend/.env` from [`backend/.env.example`](../backend/.env.example) | `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL` |
| Backend (Render) | Dashboard → Environment, or `render.yaml` `sync: false` prompts | same three, plus optional `EXTRA_ALLOWED_ORIGINS` |
| Frontend (local) | `apps/web/.env` from [`apps/web/.env.example`](../apps/web/.env.example) | `VITE_API_BASE` (blank to use the Vite proxy) |
| Frontend (build) | shell environment before `npm run build` | `VITE_API_BASE` |

`ENVIRONMENT=production` makes the API refuse to boot while `SECRET_KEY` is the
placeholder or `DATABASE_URL` still points at the local development database, and
forces the session cookie to `Secure`.

---

## 6. Post-deploy verification checklist

Run through this in order; each line is a check that a screenshot cannot fake.

- [ ] `GET /health` → `{"status":"ok", ...}` on the deployed API origin.
- [ ] `GET /health/ready` → `200` with `"database": {"status": "ok"}`.
- [ ] `GET /docs` renders the OpenAPI UI.
- [ ] Sign up in the deployed SPA, then promote the account to superuser.
- [ ] Sign in, hard-refresh a deep link (e.g. `/companies`) — the SPA must render,
      proving the Cloudflare SPA fallback works.
- [ ] Create a company and a contact; confirm both persist after a reload.
- [ ] Import a small CSV through Import Center: preview → mapping → dry run →
      run, then download the row report.
- [ ] Check `/settings` → Sessions lists the current session; sign out revokes it.
- [ ] Backup page → “Backup now”, then “Verify” returns valid.
- [ ] Activity page lists the actions above.

---

## 7. Free-tier limits worth knowing

| Limit | Effect | Mitigation |
|---|---|---|
| Render free service sleeps after 15 min | ~1 min cold start | Free uptime monitor on `/health`; keep within 750 h/month |
| Neon compute suspends after ~5 min idle | first query is slower | `pool_pre_ping` + `pool_recycle` are already configured |
| Neon 1 GB storage/project | finite space | Archive or export old records; see [BACKUP.md](BACKUP.md) |
| Render filesystem is ephemeral | uploaded files and local backups vanish on redeploy | Keep the source CSV; use the download links, and Neon's PITR |
| Workers free request limits | generous for a static SPA | Assets are cached at the edge |
| Single free API instance | the in-process rate limiter is a per-instance ceiling | Acceptable for a single-tenant deployment |

Nothing here enables billing. When a quota is exhausted the platform suspends or
throttles the free resource rather than charging for it — confirm the current
terms on the provider's own pricing page before you rely on them, since free-tier
details change.
