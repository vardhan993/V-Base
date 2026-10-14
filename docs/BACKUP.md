# Backup & recovery

V-Base stores everything in PostgreSQL. There is no local database file to copy,
so backups are logical artifacts, and recovery is either a V-Base snapshot or the
database host's own point-in-time restore.

Two mechanisms exist, and both are free:

| Mechanism | Artifact | Produced when | Best for |
|---|---|---|---|
| **Logical JSON snapshot** | `vbase_snapshot_<stamp>.json` | `pg_dump` is unavailable, or you ask for it | portable, inspectable, transactional restore through the app |
| **Physical `pg_dump`** | `vbase_dump_<stamp>.sql` (custom format) | `pg_dump` can be found | full instance-level recovery with `pg_restore` |

The Backup page shows which one your host supports (`pg_dump: Available` or
`Not installed`) and labels every artifact with its kind.

`pg_dump` is located in three steps, so a developer install works without
touching `PATH`:

1. an absolute path in `PG_DUMP_PATH`;
2. `PATH` itself (`shutil.which`, honouring `PATHEXT` on Windows);
3. the standard install directories, newest PostgreSQL major first — e.g.
   `C:\Program Files\PostgreSQL\<major>\bin` on Windows,
   `/usr/lib/postgresql/<major>/bin` on Debian/Ubuntu, `/opt/homebrew/bin`.

When it is found, `pg_dump` runs with only the binary's own directory added to a
minimal environment, so the child can load `libpq` beside it and connect with
`PGSSLMODE=prefer` (which still works against a local server without TLS). The
resolved path is shown on the Backup page and in Settings → General.

---

## 1. What is in a snapshot

A JSON snapshot contains every table in the application's `SNAPSHOT_TABLES`
list: users, companies, contacts, contact emails and phones, employment history,
lists and memberships, tags and their links, saved searches and views, import
jobs/rows/errors, duplicate candidates, verification events, activity and audit
logs, custom fields and their values, and application settings.

Key properties:

* **Sessions are deliberately excluded.** A backup file must never contain
  material that authenticates a user. Restores preserve the sessions that were
  live at the time, so a restore does not sign everyone out.
* **Validation is real.** Every artifact is parsed before it is reported as good:
  a snapshot must be valid JSON with a `tables` object whose keys are all known
  tables; a `pg_dump` file must begin with the `PGDMP` magic bytes. A truncated or
  corrupt file reports `invalid`, never a silent success.
* **Restores are transactional.** Tables are emptied and re-inserted inside a
  single transaction, and identity sequences are realigned to
  `MAX(id)` afterwards. Any constraint violation rolls the whole restore back, so
  a partially applied restore is impossible.
* **Restores are preceded by a safety snapshot.** `pre_restore_<stamp>.json` is
  always written first — that is your undo.

---

## 2. Creating a backup

### From the UI

Settings → **Backup & Restore** → **Backup now**. The result is validated
immediately, and the list shows size, kind and validation state. **Download
export** streams a full JSON snapshot to your machine.

### From the command line

```bash
python -m nexus.commands.backup create     # pg_dump if available, else JSON
python -m nexus.commands.backup create --json
python -m nexus.commands.backup list       # every artifact with its validation
python -m nexus.commands.backup verify backups/vbase_snapshot_20261013_090000.json
```

Windows: `scripts\windows\backup.bat create` (wrappers set `PYTHONPATH` for you).

### With `pg_dump` directly

```bash
pg_dump --format=custom --no-owner --no-privileges \
        --host=<host> --username=<user> --dbname=<database> --file=vbase.dump
```

Only do this where `pg_dump` is installed. On Render's free instance it is not,
which is why the application falls back to JSON snapshots there.

> Snapshot files contain real business data. They are git-ignored, and they must
> never be committed, attached to a ticket, or copied into a public bucket.

---

## 3. Restoring

### A JSON snapshot

```bash
python -m nexus.commands.backup restore backups/vbase_snapshot_20261013_090000.json
# prompts: "Restore ... over the live database? Type 'yes' to continue"
```

Non-interactive:

```bash
python -m nexus.commands.backup restore backups/vbase_snapshot_20261013_090000.json --yes
```

From the UI: Backup & Restore → **Restore** on a valid snapshot → confirm. The
API requires a **superuser** account, writes the safety snapshot, then reports the
number of rows restored and the safety-snapshot path.

### A physical `pg_dump` archive

V-Base deliberately does **not** replay a dump in-process — that step should stay
under an operator's control, next to a migration decision. The API and CLI both
print the exact command instead:

```bash
pg_restore --clean --if-exists --no-owner \
           --host=<host> --username=<user> --dbname=<database> vbase.dump

# then confirm the schema revision is at head
python -m nexus.commands.migrate upgrade
```

Restore into a **fresh database** when you can. `--clean` drops objects in the
target, so pointing it at the live database while the API is serving is a
deliberate, destructive act.

---

## 4. Host-specific recovery

### Neon (recommended free tier)

Neon keeps a point-in-time restore window on the Free plan and can fork a branch
instantly. This is the fastest disaster path and needs no artifact:

1. Neon console → your project → **Branches** → create a branch from a point in
   time just before the incident.
2. Point `DATABASE_URL` at the new branch's pooled connection string (or restore
   in place from the console).
3. Confirm `/health/ready` is green.
4. Verify counts on the Dashboard, then re-run `python -m nexus.commands.migrate upgrade`
   to make sure the schema is at head.

Neon's architecture is copy-on-write, so a branch is cheap and immediate.

### Render (free instance)

Render's filesystem is **ephemeral**: anything written to `UPLOADS_DIR` or
`BACKUPS_DIR` disappears on the next deploy or restart. Your data lives in Neon,
so recovery is Neon's job. What you must keep elsewhere is the *source data*:
original spreadsheets and any exported reports you still need.

### Self-hosted / Docker

The `docker-compose.yml` stack keeps PostgreSQL in the named volume
`vbase-db-data`. Back that volume up at the host level, or keep using the JSON
snapshots and `pg_dump` above.

---

## 5. Schema, migrations and restores

* Migrations are the only supported way to change the schema. The application
  never issues DDL at runtime.
* A snapshot records the schema revision it came from (`schema_version`). After
  restoring an older snapshot, run `python -m nexus.commands.migrate upgrade` to
  bring the schema forward.
* `python -m nexus.commands.migrate check` fails if models and migrations have
  drifted, which catches "someone edited a model and forgot the migration".
* A restore never drops or creates tables; it only replaces rows. Adding a column
  therefore does not break old snapshots.

---

## 6. Drill it before you need it

A backup you have never restored is a hypothesis. The shortest honest drill:

```bash
# 1. Note a baseline
curl -s http://127.0.0.1:8000/health/ready

# 2. Snapshot
python -m nexus.commands.backup create --json

# 3. Add a record through the UI, then restore the snapshot
python -m nexus.commands.backup restore backups/<the file you just made> --yes

# 4. Confirm the record is gone and the pre-restore app still works
#    (the response prints the safety snapshot path)
```

Point step 3 at a Neon **branch** instead of the live database to rehearse
without touching production data.

---

## 7. What backups do not cover

Be explicit about the gaps so nobody assumes more than is true:

* **Uploaded files.** Original CSVs/XLSX live on the API host's filesystem, not in
  PostgreSQL. On Render they are lost on redeploy. Keep the source files yourself.
* **Secrets.** `SECRET_KEY`, `DATABASE_URL` and any provider credentials are
  environment configuration, not data. Back them up in your own secret store.
* **Provider infrastructure.** A snapshot restores rows; it cannot recreate a
  deleted Neon project or a suspended Render service.
* **Point-in-time granularity.** JSON snapshots are as fresh as the last one you
  took. Between snapshots, Neon's PITR window is the finer-grained safety net.
* **Cross-version guarantee.** Snapshots from a much older application version
  are validated structurally, but a column that no longer exists is silently
  skipped. Always run the drill after a significant upgrade.
