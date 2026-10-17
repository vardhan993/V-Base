# V-Base go-live runbook

Operational procedures for the deployed service. Context on how the current
deployment was built lives in
[system_notes/deployment_report_2026-10-17.md](../system_notes/deployment_report_2026-10-17.md).
Backup mechanics in full depth are in [BACKUP.md](BACKUP.md); this page is the
short, ordered, "do this now" version.

## Live topology (what talks to what)

| Piece | URL / ID | Runs on |
|---|---|---|
| Frontend (SPA + `/api` proxy Worker) | https://site-fafe76a2e2c045879621f2a17e8f3493.freebuff.page (production), `site-19c554e0…` (preview) | Freebuff Sites Workers |
| API (FastAPI) | https://vbase-api.onrender.com — service `srv-db8sdemq1p3s7397k7lg` | Render free (oregon) |
| Database | project `aged-butterfly-51121482`, branch `br-divine-darkness-b4txicy6`, role `vbase_app` | Neon free (us-east-2) |
| Git | https://github.com/vardhan993/V-Base (branch `main`) | GitHub |
| Keep-alive | `.github/workflows/keep-alive.yml`, cron every 10 min → `/health/ready` | GitHub Actions |

Rule of thumb: **code lives on GitHub, rows live in Neon, files live nowhere**
(Render's disk is ephemeral — see BACKUP.md §4).

---

## 1. Routine deploys

### 1.1 Backend (Render, autoDeploy off)

```bash
# 0. Before anything: CI must be green on the commit you are shipping.
#    https://github.com/vardhan993/V-Base/actions (workflows: CI, and the
#    keep-alive pings that prove /health/ready is responding)

# 1. Trigger a deploy (uses the API key in .local-secrets/render_api_key.txt)
KEY=$(cat .local-secrets/render_api_key.txt | tr -d '\r\n')
curl -sS -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  https://api.render.com/v1/services/srv-db8sdemq1p3s7397k7lg/deploys \
  -d '{"clearCache":"do_not_clear"}'
# → returns {"id":"dep-…","status":"build_in_progress", ...}; note the id

# 2. Poll until "live" (build ≈ 2 min, migrate + start adds ~1 min)
curl -sS -H "Authorization: Bearer $KEY" \
  https://api.render.com/v1/services/srv-db8sdemq1p3s7397k7lg/deploys/<dep-id> \
  | python -c "import json,sys; print(json.load(sys.stdin)['status'])"

# 3. Smoke test (must all pass)
curl -sS https://vbase-api.onrender.com/health                 # 200 ok
curl -sS https://vbase-api.onrender.com/health/ready          # 200 ready, database.status=ok
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://site-fafe76a2e2c045879621f2a17e8f3493.freebuff.page/api/v1/auth/me  # 401
```

Migrations run automatically as part of the start command
(`python -m nexus.commands.migrate upgrade && …`), and the deploy fails loudly
if Neon is unreachable, so a broken build never serves traffic.

### 1.2 Frontend (Freebuff Sites, manual)

The Worker serves whatever was last uploaded — a code change only ships when
you deploy. Deploys must go to **both** environments you care about (they are
independent; deploying preview does not touch production).

```bash
# 1. Build — never deploy a stale dist/
cd apps/web && npm run build     # downloads none — build first, then check CI too

# 2. Deploy via Freebuff Sites (desktop app) using apps/web/deploy-manifest.json
#    (manifest is committed so the deploy is reproducible)

# 3. Smoke test on each environment you deployed
#    - hard-reload the UI (Ctrl+Shift+R) — the SPA chunk names change, but a
#      cached index.html can reference old chunks that no longer exist
#    - log in and open Dashboard + one heavy page (Analytics or Import)
#    - the URL of the loaded entry should match the fresh build
#      (grep -o 'assets/index-[^"]*\.js' against dist/index.html)
```

### 1.3 Database schema changes (Neon)

Alembic migrations are part of the backend start command, so a normal backend
deploy is the whole story — with two safety rules:

1. **Expand/contract.** Ship additive migrations (new nullable columns, new
   tables) before deploying code that uses them; never remove columns in the
   same release that stops writing them. A one-release gap is enough because
   the deployed build and the migration run in the same start command.
2. **Check drift in CI, not in prod.** `python -m nexus.commands.migrate check`
   fails when models and migrations disagree — run it locally before pushing;
   CI runs the full test suite against real PostgreSQL on every push.

### 1.4 Rollback

- **Backend:** deploys are immutable; redeploy the previous commit via 1.1 and
  Render rebuilds that commit (the service parameter is the repo + branch, so
  `git revert` or a `git checkout` of the old SHA onto a branch both work).
  The database schema may have moved forward — additive migrations are
  backward-compatible by rule 1.3.1, so an old build still runs.
- **Frontend:** redeploy the previous build with the manifest (1.2). SPA chunks
  are content-hashed, so the old bundle re-upload is safe as long as its
  referenced chunks still exist — which re-uploading guarantees.
- **Database (rows only):** see §3.

---

## 2. Environment & secret rotation

All provider credentials live in one of two places: git-ignored local files
under `.local-secrets/` (never commit them) and host dashboards. See the
table, then the rotation steps.

| Secret | Where it lives | Used by | Rotate when |
|---|---|---|---|
| `DATABASE_URL` (Neon DSN, app role `vbase_app`) | Render env vars, `backend/.env` (local) | API | password leak, role compromise, quarterly |
| `SECRET_KEY` (session/cookie signing) | Render env vars, `backend/.env` | API (auth) | leak, or any suspicion of session forgery |
| `API_ORIGIN` (backend URL for the Worker) | Freebuff Sites secret (preview + production) | Frontend Worker | only if the backend URL changes |
| Render API key | `.local-secrets/render_api_key.txt` | deploy automation | leak, or a person leaving the project |
| Neon API key | `.local-secrets/neon_api_key.txt` | provisioning scripts | leak, or a person leaving the project |
| `FRONTEND_URL`, `EXTRA_ALLOWED_ORIGINS` | Render env vars | API (CORS/CSRF allow-list) | whenever a frontend URL is added or removed |

Rotation notes:

- `EXTRA_ALLOWED_ORIGINS` is comma-separated; `FRONTEND_URL` is the primary
  origin. Both are writable per-variable via
  `PUT /services/{id}/env-vars/{KEY}` with `{"value": "..."}` — a change needs
  a redeploy (§1.1 step 1) to take effect. (The collection `PUT/PATCH /env-vars`
  endpoints return 400 "invalid JSON"; the per-variable route is the one that
  works — verified 2026-10-17.)
- Rotating `SECRET_KEY` signs everyone out (sessions are signed cookies keyed
  on it) — pick a quiet time.
- Rotating `DATABASE_URL` is two steps: create/rotate the Neon role password,
  then update the Render env var and redeploy. The old password is valid until
  you rotate it in Neon, so order matters: rotate the role first, hit the
  API with the new value, only then retire the old one.
- `.local-secrets/` is git-ignored; never commit it (verified in commit
  9d11f63). If a value has ever been pasted into chat, email, or a ticket,
  treat it as burned and rotate regardless of the schedule.

---

## 3. Backup & restore drills

Full mechanics: [BACKUP.md](BACKUP.md). What follows is the practical schedule
and the two drills to actually run.

### 3.1 Standing schedule

| Frequency | Action |
|---|---|
| Weekly | Export a JSON snapshot from **Backup & Restore → Download export** in the production UI, save it outside the server |
| Before any risky change | Manual snapshot before touching data (imports, bulk edits) |
| After every significant release | Run the restore drill below on a Neon branch |
| Monthly | Confirm at least one off-host snapshot exists and validates (`validate` on the Backup page shows the state) |

On Render, snapshots written to `BACKUPS_DIR` are **ephemeral** — gone on the
next deploy. The "Download export" path exists precisely for this; never rely
on the server-side list as your only copy.

### 3.2 Drill A — restore a JSON snapshot (do quarterly)

Goal: prove the backup format and the restore transaction work against tonight's
schema, not last quarter's.

First, get a real production snapshot: export it from the production UI
(**Backup & Restore → Download export**) and save it into `backups/` on your
machine. The backup CLI only sees a database you can reach directly
(local/staging — handy for the rehearsal itself), not the Render host.

```bash
# Build a staging database to restore into:
#   create a Neon branch (console → Branches → Create branch from a point in
#   time) and point a local shell at it:
export DATABASE_URL='postgresql+asyncpg://…@<new-branch-pooler>/neondb?sslmode=require'

# Apply the schema to the branch, then restore rows into it — NOT production
python -m nexus.commands.migrate upgrade
python -m nexus.commands.backup restore backups/vbase_snapshot_<stamp>.json --yes

# Verify
#   (restore prints rows restored + the pre-restore safety snapshot path)
# start the API locally against the branch, log in, open a records list,
# confirm row counts match the production dashboard
```

Passing criteria: restore reports rows restored + safety snapshot path; the
branch API returns `/health/ready` 200 with the expected counts.

### 3.3 Drill B — point-in-time recovery via Neon branch (do twice a year)

Goal: prove the provider-side safety net works without any artifact.

1. Neon console → project → **Branches** → create branch from a point in time
   30 minutes ago.
2. Point a local API at it (step 2 above), hit `/health/ready`, count rows.
3. Optionally promote that branch (repoint Render's `DATABASE_URL` at the new
   pooled DSN + redeploy) — that's the full disaster recovery path.
4. Document in one line how long the whole dance took; that number is your RTO.

### 3.4 After a real incident

1. Freeze: stop imports/deploys; note the time (Neon PITR window depends on it)
2. Snapshot the **current** (possibly damaged) state before touching anything —
   it is evidence and the baseline.
3. Choose one: restore rows via a snapshot taken **before** the incident
   (§3.2 pointed at production — restore requires a superuser account, and the
   pre-restore safety snapshot is your undo; read BACKUP.md §3 first) **or**
   branch-and-promote from just before the incident (§3.3 — usually safer
   when the damage is unclear, since nothing live is overwritten).
4. Re-verify: `/health/ready` 200, login works, counts sane, then rerun the
   last successful user action end-to-end.
5. Post-mortem: what data was between the snapshots, and can you shrink the
   snapshot interval?

---

## 4. Monitoring reality check

- **API up?** The keep-alive workflow doubles as a canary: every 10-minute run
  fails loudly (red X in Actions) if `/health/ready` is not 200.
- **Logs:** Render → your service → Logs (drain them if you want retention);
  Cloudflare/Sites observability for the Worker.
- **Not covered:** no external paging/alerting. If silence at 3 a.m. matters,
  add an uptime monitor that emails/calls you.
- **Free-plan ceilings to watch** (they throttle, not bill): Render 750
  instance-hours/mo; Neon 0.25 CU compute + free storage; Sites 100k req/mo +
  10k req/day; GitHub Actions free minutes.

---

## 5. One-page incident card

| Symptom | First check | Likely fix |
|---|---|---|
| Site up but API calls fail | `/health/ready` from curl | Backend asleep (keep-alive paused?) → wait 60s, retry; else §1.1 rollback |
| `503` from `/health/ready` | Neon console status | DB suspended/unreachable → resume compute, check DSN, §2 rotation if creds died |
| Login works, then 403 on writes | send Origin header | CORS list missing the frontend URL → §2 FRONTEND_URL update + redeploy |
| SPA loads old/broken | hard reload | Stale index.html cache; redeploy if chunks 404 (§1.2) |
| Deploy stuck "update_failed" | Render logs (via API or dashboard) | Usually schema/env: read the traceback before re-triggering |
| Data missing after restore | Backup page validation | Restore rolled back (transaction) → check snapshot validity, re-read BACKUP.md §3 |
