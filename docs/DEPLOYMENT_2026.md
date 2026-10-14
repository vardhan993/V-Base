# Deployment notes (2026-10-15) — verified state

## Architecture (identified, not changed)

- **Frontend**: React 19 + Vite 6 + TypeScript SPA in `apps/web`, built to `dist/`,
  served by a Cloudflare Worker (`apps/web/worker/index.js`) that also reverse-proxies
  `/api/*` to the backend. Config: `apps/web/wrangler.jsonc`.
- **Backend**: FastAPI (`backend/src/nexus/app.py`), async SQLAlchemy 2 + asyncpg,
  Pydantic v2, Alembic migrations with `pg_trgm`/`tsvector` indexes.
- **Database**: PostgreSQL only. The code requires a real Postgres server; it is NOT a
  Cloudflare D1 / SQLite app. Free-tier recommendation stays **Neon** (already
  documented in docs/DEPLOYMENT.md §1). Do not swap to D1 — the backend is a Python
  runtime process, not a Worker.
- **Auth**: Argon2 password hashing, server-side sessions in an HttpOnly cookie,
  CSRF double-submit, exact Origin allow-list, admin gated server-side in
  `backend/src/nexus/api/deps.py`. All admin checks live in the API, never the SPA.
  Frontend bundle contains no secrets.

## What was actually run and passed (this session)

- `python -m compileall src` — clean.
- `import nexus.database` / `import nexus.app` — OK; 32 tables load from metadata.
- `npm run build` in apps/web (tsc −b + vite build) — succeeded. Only warning is a
  ~1.9 MB main chunk (gzip 424 kB); consider manualChunks later, non-blocking.
- `python -m pytest tests -q` — **278 passed** against real PostgreSQL
  (local container on 127.0.0.1:5433, `vbase_test`).
- Fixed on the way:
  1. `backend/src/nexus/database/__init__.py` — removed a stray `]` that broke the
     module, and de-duplicated `__all__`.
  2. `backend/src/nexus/api/v1/saved_views.py` — `_normalise_list` typo (NameError)
     fixed; sorted-view serialization restored.
  3. Environment lacked `alembic` and `asyncpg`, which silently skipped the entire
     test suite ("skipped: PostgreSQL not available"). Installed both; the suite
     then ran for real. **Record these in CI requirements** so skips can't hide
     regressions.

## Not done / not claimed

- Nothing has been deployed to Neon, Render, or Cloudflare. Don't trust any
  "deployed" until the checklist below is run against the live URL.
- No Git push, no commit was made; changes are in the working tree.

## Manual setup required (dashboard work, cannot be scripted)

1. **GitHub** — push the repo; keep `.env*`, `backups/`, `uploads/` ignored
   (they already are; verify secrets never entered history, else rotate, not just delete).
2. **Database** — follow docs/DEPLOYMENT.md §1: create Neon project (free tier),
   enable the pg extensions Alembic creates, copy the DSN.
3. **Backend** — docs/DEPLOYMENT.md §2: import render.yaml on Render, set env vars,
   apply Alembic migrations, verify /api/v1/auth boots.
4. **Frontend** — docs/CLOUDFLARE.md: set `VITE_API_ORIGIN` before building,
   `npm run build`, `wrangler deploy` or connect via GitHub → Cloudflare Workers
   build with the same build command and `dist` output directory.
5. **Secrets hygiene** — only `.env.example` files are tracked; .env is gitignored.
   Rotate any database password that has ever touched chat or email.

## Beginner launch checklist

- [ ] Site opens over HTTPS on mobile + desktop (Workers free subdomain first)
- [ ] Register → login → logout → login again (tmp mail irrelevant; use your own
      test address, then change the password)
- [ ] Normal user cannot call admin API endpoints directly (test with curl or the
      browser dev tools, not just hidden buttons)
- [ ] CRUD works and survives refresh (server-side persistence in Neon)
- [ ] Forms reject missing/invalid data (400s, not 500s)
- [ ] No secrets in the deployed JS bundle (`dist/assets/*.js`) — search for
      "postgres", "sslmode", "SECRET_KEY"
- [ ] Backups: Neon free branch/pit-point restore is understood before importing
      real customer data; the app's own backup command is documented in docs/BACKUP.md
- [ ] Errors visible: Render log drain + Cloudflare observability enabled
- [ ] Usage limits understood: Neon free plan hours/GB, Render free plan spins down,
      Cloudflare Workers free plan 100k req/day — none of these bill you, they throttle
- [ ] Billing alerts: none should exist since nothing is on paid plans — leave it that
      way until you choose paid upgrades deliberately

## When you outgrow free

- Render free CDN spins idle services down ~15 min inactivity → backend upgrade is
  usually the first paid need.
- Neon free plan scales storage/branch quotas.
- A custom domain on Cloudflare is free; buy/register the domain at any registrar.
