# Deployment report — 2026-10-17

## Result: backend live and fully verified end-to-end

- **Backend (Render)**: https://vbase-api.onrender.com — deploy `dep-db9ha261egvs73f96clg`
  is **live**. Free instance, oregon, rootDir `backend`, autoDeploy off (deploys deliberate via API).
- **Database (Neon)**: `vbase-prod` project `aged-butterfly-51121482`, app role `vbase_app`,
  pooled endpoint `ep-quiet-glitter-b4vkjh16-pooler.c-6.us-east-2.aws.neon.tech`, sslmode=require.
- **Frontend (Freebuff Sites)**: **both environments live as of 2026-10-17 (updated later the same day):**
  - Preview:  https://site-19c554e0baae495abaaa485b2ef57dbb.freebuff.page
  - Production: https://site-fafe76a2e2c045879621f2a17e8f3493.freebuff.page
  Both serve the upgraded SPA build (`index-CUMn4Usq.js`) with the `API_ORIGIN` secret set,
  proxying `/api/*` to Render (CSS and images asset paths updated in the bundle).

## Root cause of the original failure, and the fix

The failed deploy (`dep-db8sdf6q1p3s7397k95g`, commit 2a0b57a) died during startup, not build:

```
alembic.util.exc.CommandError: Path doesn't exist:
/opt/render/project/src/.venv/lib/python3.12/alembic
```

`nexus.commands.migrate` resolved the Alembic script directory relative to a guessed backend
root (`Path(__file__).parents[3]`), which lands inside site-packages under a pip install, so the
start command aborted before uvicorn could bind its port (Render then reported the port-scan timeout).

**Fix (commit `9d11f63`, pushed to main):** migrations now live inside the package
(`backend/src/nexus/migrations/`) and ship in the wheel (`script.py.mako` as package data);
the script location is resolved from the installed package. Also updated:
`backend/alembic.ini` (local CLI helper → `src/nexus/migrations`), `tests/backend/conftest.py`,
`backend/Dockerfile` comment, `docs/NEON.md`, and the `alembic -c ...` hint in `apps/web/src/pages/backup.tsx`.

## Env var changes made on the service (via Render API, single-var PUT)

- `FRONTEND_URL` = `https://site-19c554e0baae495abaaa485b2ef57dbb.freebuff.page` (the SPA origin)
- `EXTRA_ALLOWED_ORIGINS` = `https://vbase-api.onrender.com`
- (Unchanged: `DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT=production`, pool sizing 5/5/300,
  rate limits, uploads/backups dirs, `PYTHON_VERSION=3.12.11`.)
- Note: `PATCH /services/{id}` returned 200 but silently ignored env changes, and
  `PUT/PATCH /env-vars` (collection) return 400 "invalid JSON" —
  `PUT /services/{id}/env-vars/{KEY}` with `{"value": "..."}` is the endpoint that works.

## What was verified (live URL)

| Check | Result |
|---|---|
| `GET /health` | 200 `{"status":"ok",...}` |
| `GET /health/ready` | 200 ready; DB ok, pool used 0/5 |
| Unauthenticated `GET /api/v1/auth/me` | 401 `Not authenticated` (correct) |
| Write without Origin header | 403 `Missing Origin/Referer header` (correct) |
| CORS origin allow-list | allows the Worker origin |
| Signup → login → `me` (curl, real DSN) | 201 → 200 → 200 (session cookie `HttpOnly; Secure; SameSite=lax`) |
| Signup through the real browser UI | landed on the authenticated dashboard with sidebar/topbar/user loaded |
| Worker proxy `SPA → /api/*` (browser) | API calls succeed same-origin |
| Deployed JS bundle secret scan | no DSN/secret material; only UI placeholder strings |
| Smoke test users created during verification | deleted (cascade + user row, remaining 0) |

## Not done / known limits

- Rebuild + redeploy after frontend changes: `npm run build` in apps/web, then Sites → deploy
  with `apps/web/deploy-manifest.json` for each environment you want updated.
- Custom domain not configured on the Worker or Render.
- **Cold-start mitigation (added 2026-10-17, commit fd25ae6):** the scheduled
  GitHub Actions workflow `.github/workflows/keep-alive.yml` pings
  `/health/ready` every 10 minutes so the Render free instance never sits
  idle for its 15-minute spin-down window, and Neon's compute stays awake.
  Verified with a manual workflow_dispatch run (run 39014327197, conclusion
  `success`). Ping target is overridable via the repo Actions variable
  `RENDER_HEALTH_URL` if the host changes. First scheduled run may be
  delayed a few minutes by GitHub; that slack is safe for a 15-min timeout.
- Render free plan spins the API down after ~15 min idle (~1 min cold start on next request).
- The SPA bundle (~1.7 MB main chunk) could be code-split later for faster first paint; non-blocking.
- Local `.local-secrets/` holds the Neon + Render API keys — gitignored (commit `9d11f63`), never commit it.
- openapi.json/docs endpoints return 404 in production (docs disabled) — intentional, not a fault.

## How to redeploy later

```bash
KEY=$(cat .local-secrets/render_api_key.txt | tr -d '\r\n')
curl -sS -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  https://api.render.com/v1/services/srv-db8sdemq1p3s7397k7lg/deploys \
  -d '{"clearCache":"do_not_clear"}'
```
