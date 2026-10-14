# Neon (free PostgreSQL) — launch checklist

The backend **requires real PostgreSQL** (asyncpg + `pg_trgm` trigram search +
`tsvector` indexing). Neon's free plan is the recommended provider; nothing here
bills you — quotas throttle, not charge.

## 1. Create the project

1. Sign up at https://neon.tech (no credit card for the free plan).
2. Create a project named `vbase`.
3. Copy the **pooled connection string** from the dashboard. Convert it to the
   async form the app expects:

   ```
   postgresql+asyncpg://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/neondb
   ```

   Neon inserts `?sslmode=require`; the app's `build_connect_args` applies SSL
   to asyncpg automatically — keep the parameter, don't strip it.

## 2. Point the backend at it

- **Local**: put the DSN in `backend/.env` as `DATABASE_URL=...`. This file is
  gitignored — never paste the real DSN into any tracked file, chat, or the
  frontend.
- **Render** (when you get there): add `DATABASE_URL` as an environment variable,
  not a build setting.

## 3. Run migrations with the exact command verified locally (2026-10-15)

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://...@ep-xxxx-pooler.../neondb python -m alembic upgrade head
```

Then confirm models still match the database:

```bash
cd backend
DATABASE_URL=... python -m alembic check
# expected: "No new upgrade operations detected."
```

**Verified locally** (against a throwaway Postgres database, then dropped):
`upgrade head` applies 0001_initial → 0005_email_sequences, creates **33 public
tables** (32 app tables + `alembic_version`), and the migrations create
`pg_trgm` themselves — no manual extension step is needed. `alembic check`
reported no drift between migrations and models.

## 4. Launch checklist for the database

- [ ] `alembic upgrade head` completes with the Neon DSN
- [ ] `alembic check` reports no upgrade operations
- [ ] Register one test user through the API and confirm it persists in the Neon console
- [ ] Backups understood: check the Neon dashboard → *Backups / PITR* for the
      free plan's restore window before importing real customer data
- [ ] App-level backups: `docs/BACKUP.md` describes `vbase-backup` snapshots
      (dumps selected tables to `backend/backups/`); schedule one locally if you
      need copies outside Neon
- [ ] DSN appears in exactly two places: `backend/.env` (gitignored) and Render
      env vars — nowhere else, and never in the frontend
- [ ] Free-plan limits noted: the branch auto-suspends after ~5 minutes idle
      (first request after that is slower), storage/compute-hours quotas visible
      in the Neon console

## 5. If something fails

- `FATAL: ... password authentication failed` → wrong DSN or it lost the password.
- `CREATE EXTENSION` errors on `pg_trgm` → you're on a role without permission
  (use the project owner role from the connection string).
- Idle-timeout disconnects during long imports → retry; Neon free suspends idle
  compute, and asyncpg reconnects.
