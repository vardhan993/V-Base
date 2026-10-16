# V-Base — Go-Live Playbook (Neon → Render → Cloudflare)

Repo state: `main` @ `a3b25f2` pushed to `github.com/vardhan993/V-Base`.
Backend tests 277/277 pass, frontend build clean, migration 0006 is head.
Per your choices on 2026-10-16: existing Neon DB, existing Render service, manual Cloudflare Worker deploy.

---

## 1. Secrets to add (Sites → Secrets, NEVER in chat)

Open the Freebuff **Sites** panel → project `vbase` → **Secrets** and add:

| Secret name | Value | Where the value comes from |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/NEONDB?sslmode=require` | Neon console → project → **Connection string → pooled**. Rewrite the scheme to `postgresql+asyncpg://` exactly like that; keep `?sslmode=require`. |
| `RENDER_API_URL` | `https://vbase-api.onrender.com` (or the existing service's URL) | Render dashboard → the service's URL, **no trailing slash** |

Once both exist, say "continue" and I will: run `alembic upgrade head` + `alembic check`
against Neon from your local checkout (reading the secret file contents from disk, not chat),
then run the end-to-end smoke tests against the live origins.

---

## 2. Render — env vars on the existing service

Render dashboard → **vbase-api** → **Environment** → add/confirm:

| Key | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | same asyncpg DSN as above |
| `SECRET_KEY` | fresh value from `python -c "import secrets; print(secrets.token_urlsafe(48))"` (generate locally; only into Render's field, never chat) |
| `FRONTEND_URL` | exact Cloudflare Worker origin once deployed, e.g. `https://v-base.<subdomain>.workers.dev`, **no trailing slash** |
| `EXTRA_ALLOWED_ORIGINS` | optional extra origins |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `5` |
| `DB_POOL_RECYCLE` | `300` |
| `UPLOADS_DIR` / `BACKUPS_DIR` | `/tmp/vbase/uploads` / `/tmp/vbase/backups` |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `10` |

Then **Manual Deploy → Clear build cache & deploy**. Health check path is already
`/health/ready` per `render.yaml`.

Migrations: the `render.yaml` start command runs `python -m nexus.commands.migrate upgrade`
at boot, so a healthy deploy log confirms migrations reached head. If it didn't,
say "continue" after adding the DATABASE_URL secret and I'll run
`alembic upgrade head` against Neon from your machine.

---

## 3. Cloudflare — replace the stub Worker with the real SPA + proxy

The `v-base` Worker currently deployed is a "Hello world" template. The repo's
`apps/web/wrangler.jsonc` + `apps/web/worker/index.js` are the real deployment
(SPA static assets + same-origin `/api/*` proxy via `API_ORIGIN`).

### Option A — from your terminal (recommended, ~3 min)
```bash
cd /d/V-Base/apps/web
# create an API token first (section 4), then:
export CLOUDFLARE_API_TOKEN=<paste-token>
npm run build
# set the backend origin in wrangler.jsonc first:
#   "vars": { "API_ORIGIN": "https://vbase-api.onrender.com" }
npx wrangler deploy
```
Note: `wrangler.jsonc` has `"name": "vbase"` while the stub Worker is named `v-base`
(dash). Wrangler will deploy a **new** worker `vbase`; afterwards you can delete the
stub `v-base` in the dashboard. To reuse the `v-base` name instead, change `"name"`
in wrangler.jsonc to `v-base` before deploying.

### Option B — dashboard-only
1. **Workers & Pages → Create → Workers → Connect to Git** → `vardhan993/V-Base`.
2. Root dir `apps/web`, build command `npm ci && npm run build`, output dir `dist`.
   This uses the existing `wrangler.jsonc`.
3. Deploy once, then **Settings → Variables** add
   `API_ORIGIN = https://vbase-api.onrender.com` (plain variable, not a secret).
4. **Settings → Domains & Routes**: enable the `workers.dev` subdomain
   (the existing stub has it disabled — that's why it returns 403 externally).

### After deploy, set the backend allow-list
`FRONTEND_URL` on the Render service must exactly equal the deployed Worker origin
(or add it to `EXTRA_ALLOWED_ORIGINS`). Otherwise every POST/PATCH/DELETE from the
SPA gets `403 Origin not allowed`.

---

## 4. Cloudflare API token (only if you want me to deploy via API instead)

dash.cloudflare.com → My Profile → **API Tokens → Create Token** → custom:
- Account: *Workers Scripts: Edit*, *Account Settings: Read*
- Zone resources: none needed
- Expires: 7 days
Save it as secret `CLOUDFLARE_API_TOKEN` in Sites → Secrets and say "continue".

---

## 5. Post-deploy smoke tests (I run these once origins exist)

- `GET /api/v1/health` through the Worker origin → 200
- signup → login → CSRF-negative write → logout, using test-only credentials
- contacts CRUD + export download (`Cache-Control: no-store`, formula-injection guard)
- `alembic check` against Neon reports no drift
- bundle scan: no `localhost`, no DSN in `dist/assets/*.js`

## 6. Backups / recovery
- Neon: confirm a point-in-time snapshot exists in the console before importing real data.
- App-level snapshots: `docs/BACKUP.md` (`/settings/backup` endpoint).
- Restore drill: `pg_restore` into a scratch DB — **still not executed**; do once after go-live.
