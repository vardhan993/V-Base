# Render halted — root cause (chat checkouts)

## What users saw
The app screen was inert: no sidebar, no topbar, no routes, and in some cases only a
non-interactive "Loading Nexus Intelligence" spinner. Pages, menus, and auth-dependent UI
did not render.

## Root cause
`backend/src/nexus/api/v1/settings.py` was not a real router module. It was a
documentation/note draft that looked enough like code to be imported, but it had:

- functions defined late in the file and referenced earlier (`_db_size`, `_last_backup_date`),
- flow that bypassed the router builder,
- no clean FastAPI `@router` tree for `/settings/app`, `/settings/preferences`,
  `/settings/backup`, `/settings/restore`, `/settings/export-db`, `/settings/download-db`,
  `/settings/keys`.

That file was imported through the normal router assembly path, so the settings endpoints never
actually registered. The frontend depends on those settings endpoints during startup and from
the Settings page, so auth/startup/page rendering could stall whenever that module was loaded, and
startup/settings-dependent UI could refuse to paint.

## Why it could look "almost fine" in some sessions
If the broken module was never imported, or if its text was evaluated as prose rather than as code,
the rest of the app could start. In chat-driven checkouts the file often ended up as plain text and
was never registered as a working router, so the app could boot but the settings-backed startup path
and Settings page remained unreliable.

## Fix applied
Replaced `backend/src/nexus/api/v1/settings.py` with a real, coherent settings router that:

- defines helpers before they are referenced,
- uses a single `@router` object for all settings endpoints,
- exposes `/settings/app`, `/settings/preferences`, `/settings/keys`,
  `/settings/backup`, `/settings/restore`, `/settings/export-db`, `/settings/download-db`.

No new dependencies were introduced. No existing route names or frontend contracts were changed.

## Verification approach
1. Start the backend and confirm the settings endpoints respond:
   - `GET /api/v1/settings/app`
   - `GET /api/v1/settings/preferences`
   - `PATCH /api/v1/settings/preferences`
   - `POST /api/v1/settings/backup`
   - `GET /api/v1/settings/export-db`
   - `GET /api/v1/settings/download-db`
2. Start the frontend and confirm:
   - Auth-gated routes render after sign-in,
   - The Settings page loads app info and preferences without console errors,
   - The topbar, sidebar, and command palette are visible.

## Files involved
- `backend/src/nexus/api/v1/settings.py`
- `backend/src/nexus/api/v1/routers.py`
- `frontend/src/app/App.tsx`
- `frontend/src/components/topbar.tsx`
- `frontend/src/lib/store.ts`
- `frontend/src/pages/settings.tsx`

## Why this matters for chat checkouts
Chat sessions sometimes import or paste code as text rather than as a live module. A router file
that is only superficially "code-shaped" can be read as notes and then quietly break the running
app. This fix keeps the settings router on the same contract the frontend already expects, so the
app can actually render again without changing the UI or API surface.
