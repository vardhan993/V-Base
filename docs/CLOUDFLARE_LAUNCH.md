# Launching the frontend on Cloudflare (connected to your GitHub repo)

The SPA + `/api/*` reverse proxy ships as one **Cloudflare Worker** configured by
`apps/web/wrangler.jsonc`. The Workers build system builds it straight from the
`github.com/vardhan993/V-Base` repo — no local tooling needed. (Prefer deploying
from your machine instead? `docs/CLOUDFLARE.md` covers `npx wrangler deploy`.)

Expected free-tier URL shape: `https://vbase.<your-subdomain>.workers.dev`.

## A. Connect the repo

1. Cloudflare dashboard → **Workers & Pages → Create → Workers → Import a repository**.
2. Authorize Cloudflare for GitHub and select `vardhan993/V-Base`.
3. Build settings — enter them exactly:

   | Field | Value |
   |---|---|
   | Name | `vbase` |
   | Production branch | `main` |
   | Working directory | `apps/web` |
   | Build command | `npm run build` |
   | Deploy command | `npx wrangler deploy` |

4. **Build variables** → add:
   - `VITE_API_ORIGIN` = your backend origin (e.g. `https://vbase-api.onrender.com`,
     no trailing slash). This is compiled into the bundle at build time — set the
     variable before the build runs, and rebuild when the backend URL changes.
5. Deploy.

   The Workers Builds image defaults to Node.js 24 (22 also preinstalled),
   which satisfies the lockfile-pinned wrangler (Node >= 22 requirement).
   If you ever override `NODE_VERSION`, keep it at 22 or higher.

## B. Runtime variable for the `api` proxy

The Worker routes `/api/*` to `env.API_ORIGIN` ([worker/index.js](../apps/web/worker/index.js)).
After the first build, on the Worker → **Settings → Variables and Secrets**, add
the plain (non-secret) variable:

- `API_ORIGIN` = same backend origin as `VITE_API_ORIGIN`.

While it's empty the site loads but `/api/*` answers a clear 503 — by design, so
you can tell "backend missing" from "backend broken".

## C. Verify before calling it deployed

- [ ] `https://vbase.<subdomain>.workers.dev` loads the app over HTTPS
- [ ] DevTools → Network: an `/api/...` call returns from the same origin (no
      CORS), and the session cookie is first-party after login
- [ ] A normal (non-admin) user cannot reach admin-only endpoints directly —
      admin checks are server-side in `backend/src/nexus/api/deps.py`, never in
      the SPA; hide-nothing logic must never be the only guard
- [ ] No secrets in the deployed JS: search `apps/web/dist/assets/*.js` for
      `postgres`, `sslmode`, `SECRET_KEY` — there should be zero hits
- [ ] Register → login → logout → login again works end-to-end
- [ ] Everything still green on the GitHub Actions `CI` check for the latest push (backend tests + frontend build + wrangler config validation)

## D. Free-plan numbers (worth knowing, none bill you)

- 100,000 requests/day on Workers free
- Bundled resources limit is generous for this app (assets under 100 MiB total)
- Observability is already enabled in `wrangler.jsonc` — check **Logs** on the
  Worker page after deploy instead of adding an extra error service for now

## E. Custom domain (optional, later)

Workers → `vbase` → **Settings → Domains & Routes → Add → Custom domain**. The
domain must be hosted on Cloudflare DNS; SSL is automatic. Register the domain
at any registrar first (that's a purchase — optional; the workers.dev URL is
fully functional for launch).

## F. Push-triggered deploys

Every push to `main` rebuilds and redeploys automatically once the repo is
connected (production branch = `main`). PR previews: the Workers Builds
integration can enable preview builds for other branches from the build settings.
