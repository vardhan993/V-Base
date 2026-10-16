# V-Base CRM — Production Readiness & Security Audit

Date: 2026-10-16 · Scope: full repo (React 19 + Vite SPA in `apps/web`, FastAPI in `backend`, PostgreSQL via async SQLAlchemy/Alembic, Cloudflare Worker static-assets + `/api/*` proxy, Render hosting target).

## Verdict: GO (conditional)

Production *code* is in good shape. The remaining items are **configuration and operator actions**, not code changes. Do not go live until the P1 configuration items below are done.

---

## Completed this session (verified)

| Item | Result |
|---|---|
| Backend test suite (real PostgreSQL `vbase_test`) | ✅ **277/277 pass** |
| Alembic migrations on dev DB (`vbase`) | ✅ Applied to head `0006_crm_engagement` (calls/notes/campaigns tables now exist) |
| Frontend `tsc --noEmit` | ✅ Clean |
| Frontend production build (Vite) | ✅ Built; one advisory warning: single 1.9 MB JS chunk (consider code-splitting later—not a blocker) |
| Imported CSV/XLSX data deleted at user request | ✅ `uploads/` emptied (3 workbooks + old report removed, `.gitkeep` kept); DB confirmed 0 import jobs / contacts / companies; UI Import history shows (0); a prior full backup exists at `backups/vbase_full_imported_data_backup.dump` |
| Dev servers | ✅ Backend :8000, Vite :5173, dockerized Postgres :5433 all healthy; preview browser verified the app live |

## Code changes made

1. **`tests/backend/test_gmail.py`** — fixed a flaky tampering test: when the HMAC's last hex char happened to be `0`, the mutation was a no-op and verification correctly succeeded. Mutation now guaranteed non-identical.
2. **`backend/src/nexus/api/v1/exports.py`** — added `Cache-Control: no-store` to CSV/XLSX export responses (sensitive CRM records must never sit in shared caches) and `_safe_cell()`, which neutralizes spreadsheet formula injection (`=`, `+`, `-`, `@`, tab, CR) by prefixing `'` in CSV and XLSX cells.
3. **`.github/workflows/ci.yml`** — least-privilege CI: top-level `permissions: contents: read` (validated with yaml-lint).

No security controls were weakened; no existing behavior removed.

---

## Prioritized findings

### P0 — none open
No leaked secrets, no unauthenticated privileged route, no broken auth primitive was found.

### P1 — must fix before go-live (configuration, not code)
1. **Prod secrets must be server-side only.** Real `DATABASE_URL`, `SECRET_KEY`/session secret, Gmail OAuth client secret, email/webhook secrets go in Render env (secret manager) and Cloudflare Secrets — never in `.env` committed, never in `VITE_*` vars, never in wrangler `vars`. Scan confirmed tracked files and git history contain **only placeholders/localhost DSNs** (`git log --all --diff-filter=A` found no `.env`, `.pem`, `.sql`, `.dump`, credential files ever committed). Keep it that way.
2. **`API_ORIGIN`** — plain non-secret Worker *variable*, set to the exact Render backend origin (e.g. `https://vbase-api.onrender.com`). Verified the Worker validates it as an absolute URL and returns clear 503/502 JSON otherwise; it forwards no spoofable identity trust (only standard `x-forwarded-*` hop headers).
3. **Cookie/Origin allow-list:** `settings.allowed_origins` must include exactly the production Worker origin; `cookie_secure` auto-enables in production (`session_cookie_secure or is_production`) — verified. The CSRF cookie stays deliberately non-HttpOnly (required by the double-submit design); the session cookie is HttpOnly + SameSite=Lax + Secure.
4. **DB TLS:** Neon/Tiger Cloud DSN must carry `?sslmode=require` (or verify-full + CA). The code's pooler detection (`build_connect_args`/`is_transaction_pooler`, covered by tests) is in place.

### P2 — should fix soon (none block launch)
- **In-process rate limiter** is per-instance (documented in code). Fine on Render Free's single instance; if you ever scale to >1 instance, move limits to Redis/DB-backed counters.
- **Single 1.9 MB bundle** — add route-level `lazy()` code-splitting to cut initial payload.
- ~~`ci.yml` workflow has no explicit `permissions:` block~~ — **fixed**: added top-level `permissions: contents: read` and validated with yaml-lint.
- Gmail OAuth state TTL (600 s) and refresh-token handling verified sound (send-only `gmail.send` scope, refresh token enforced, token cache keyed by client+refresh token).

### P3 — hardening backlog (informational)
- Rate limiter keyed on `X-Forwarded-For` first value — correct behind Render's proxy; revisit if the topology changes.
- `pg_dump`-based backups require a Postgres client on the host; JSON snapshot fallback is verified and validated (destination directory naming uses timestamps; restore procedure documented in `docs/BACKUP.md`).

---

## Verified-secure summary (what the audit checked)

- **Secrets:** tracked files + full git history clean of credentials; bundle scan clean (no API keys, no localhost API base; the two `localhost` hits are library internals and a help-text `curl` example in `backup.tsx`); frontend uses relative `/api/v1` by default (`VITE_API_BASE` override only if explicitly set).
- **Auth:** Argon2id (t=3, m=64 MiB) password hashing; DB-backed sessions storing **SHA-256 token hashes** (never raw tokens); password change + logout revoke other sessions; session/CSRF cookie flags correct; CSRF double-submit with constant-time compare; exact Origin allow-list with Referer fallback; rate limiting on credential paths (10/min) and writes; superuser checks on admin routes (`require_superuser` on email admin, settings admin, user management, session cleanup).
- **Worker proxy:** same-origin proxying, manual redirects, no caching of API responses introduced, `/api/*` → backend with query + body preserved.
- **Migrations:** linear chain 0001→0006, single head `0006_crm_engagement`, applied to dev DB without destructive ops.
- **New CRM surfaces:** calls/notes/campaigns models exported; routers wired; snapshot table list includes all new tables (backup completeness); exports + vCard auth-guarded; import job path traversal guarded (`uploads` root confinement verified in code).

---

## Go-live checklist (exact manual steps)

1. **Render (backend):** create Web Service from repo; env: `DATABASE_URL` (Neon/Tiger pooled DSN, `sslmode=require`), `SESSION_SECRET`, `EXTRA_ALLOWED_ORIGINS` or allowed-origin config = Cloudflare site origin, `FRONTEND_URL` = same, email/Gmail OAuth secrets. Migrations run via release command (`alembic upgrade head`) or manually once.
2. **Cloudflare (frontend):** `cd apps/web && npm run build && wrangler deploy --var API_ORIGIN=https://<render-origin>`; confirm `/api/v1/health` proxied, SPA deep links resolve, no `/api` caching.
3. **Neon/Tiger Cloud:** least-privilege role for the app; TLS enforced; do not expose public endpoints beyond the provider's default.
4. **Smoke tests (must pass before declaring ready):** signup → login → CSRF-blocked negative test → contacts CRUD → import cycle → export download → backup create → logout; verify HSTS + Secure cookies on production origin.
5. Rotate anything that was ever pasted into a chat or shared machine, as policy — none were found committed.

---

## Unresolved risks
- Rate-limit accuracy behind multi-instance scaling (per-instance only) — acceptable now, revisit on scale-up.
- Cloudflare-adjacent settings (page rules, WAF) are outside the repo and unverified from here.
- The full-restore drill was reviewed against `docs/BACKUP.md` and the backup file was validated by the app's own validator, but a **live restore into a scratch database has not been executed in this session** — do that once before trusting disaster recovery.
