# V-Base on Cloudflare (frontend only)

Cloudflare hosts **only the static frontend** — the built React SPA. The API and
the database live elsewhere; see [DEPLOYMENT.md](DEPLOYMENT.md) for the full
three-component setup.

| Component | Host | Why |
|---|---|---|
| SPA (this document) | Workers Static Assets | Static files at the edge, free plan, zero server code |
| API | Render free Python service | Cloudflare's Python runtime cannot run async SQLAlchemy + pandas (see below) |
| Database | Neon serverless PostgreSQL | Genuine free tier, `pg_trgm` support |

## Why the backend is not on Cloudflare

Cloudflare's Python Workers run CPython compiled to WebAssembly (Pyodide) inside
a V8 isolate. Cloudflare's own Hyperdrive documentation states that **only
synchronous SQLAlchemy is supported** and that async SQLAlchemy is unavailable
because the runtime lacks `greenlet`. V-Base's entire data layer is async
SQLAlchemy over `asyncpg`, and the import pipeline depends on `pandas` +
`openpyxl`, which are not available as PyEmscripten wheels.

Sources:

- <https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/>
- <https://developers.cloudflare.com/workers/languages/python/packages/>
- <https://developers.cloudflare.com/hyperdrive/examples/python-workers/>

This is exactly the compatibility check the brief asked for, and it fails. The
API therefore runs on a real Python host, and Cloudflare serves the frontend.

## Configuration

[`apps/web/wrangler.jsonc`](../apps/web/wrangler.jsonc) is an **assets-only**
deployment — there is no Worker script:

```jsonc
{
  "name": "vbase",
  "compatibility_date": "2026-10-01",
  "assets": {
    "directory": "./dist",
    "not_found_handling": "single-page-application",
    "html_handling": "auto-trailing-slash"
  },
  "observability": { "enabled": true }
}
```

`not_found_handling: "single-page-application"` is what makes a hard refresh on a
deep link such as `/companies/42` render the app instead of returning a 404. Do
not remove it.

## Build and deploy

```bash
cd apps/web

# 1. Point the build at the API. Vite inlines this at build time, so it must be
#    set before building — changing it afterwards has no effect.
#    Values from apps/web/.env are used automatically.
cat > .env <<'EOF'
VITE_API_BASE=https://vbase-api.onrender.com/api/v1
EOF

npm ci
npm run build        # -> dist/

# 2. Validate the config without uploading anything.
npx wrangler deploy --dry-run

# 3. Deploy (requires a free Cloudflare account: npx wrangler login).
npx wrangler deploy
```

Then set `FRONTEND_URL` on the API to the exact deployed origin — for example
`https://vbase.your-subdomain.workers.dev` — and redeploy the API. The API
requires an exact origin match, so a missing or trailing-slash-different value
shows up as `403 Origin not allowed` on any POST/PATCH/DELETE.

Deploying through the Cloudflare dashboard instead of the CLI: connect the
repository, set the root directory to `apps/web`, the build command to
`npm ci && npm run build`, the build output to `dist`, and add `VITE_API_BASE` as
a build-time environment variable.

## Same-origin alternative

If you would rather avoid CORS entirely, put the API behind a path on the same
domain. A small Worker with an assets binding can proxy `/api/*` to Render and
serve everything else from `dist/`:

```js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      const target = new URL(url.pathname + url.search, "https://vbase-api.onrender.com");
      return fetch(new Request(target, request));
    }
    return env.ASSETS.fetch(request);
  },
};
```

With that arrangement `VITE_API_BASE` can stay blank (the SPA already defaults to
`/api/v1`) and `FRONTEND_URL` on the API becomes the Worker's own origin. The
existing `wrangler.jsonc` does not include a Worker script; add `"main"` only if
you take this route, and re-run `--dry-run` afterwards.

## Caching and headers

Cloudflare caches hashed assets from `dist/assets/` automatically because Vite
stamps a content hash into every filename. `index.html` is served without a long
cache so a new deploy is picked up immediately.

Security headers for the API are set by the API itself
(`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and HSTS in
production). If you want them on the static responses too, add a `_headers` file
next to `index.html` in `dist/` at build time.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 Origin not allowed` on writes | `FRONTEND_URL` does not exactly match the browser origin | Set it to the deployed origin with no trailing slash; add extras to `EXTRA_ALLOWED_ORIGINS` |
| CORS error in the browser console | API origin missing from the allow-list | Same fix as above, then redeploy the API |
| 404 on hard refresh of a deep link | SPA fallback not applied | Keep `not_found_handling: "single-page-application"` |
| API calls go to the wrong host | `VITE_API_BASE` changed after the build | Rebuild — the value is compiled in |
| Session cookie not stored | Frontend and API on different top-level sites with `SameSite=Lax` | Use the same-origin proxy pattern above, or serve both from the same registrable domain |
| `wrangler deploy` complains about missing `main` | An older Wrangler, or a config edited to expect a Worker | Assets-only deployments need no `main` on Wrangler 4.x (`npx wrangler --version`) |

## Free-plan notes

Workers' free plan covers static asset requests generously for a single-tenant
internal tool. There is no server-side compute here, so there is no request-time
CPU budget to exceed and no Worker to keep warm — the SPA is fetched once and
cached at the edge.
