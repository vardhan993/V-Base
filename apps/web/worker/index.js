// ---------------------------------------------------------------------------
// V-Base frontend Worker (Cloudflare Workers Static Assets)
//
// Serves the built React SPA from the assets binding and reverse-proxies every
// `/api/*` request to the FastAPI backend configured in `API_ORIGIN`.
//
// Proxying on the same origin is deliberate: the API sets an HttpOnly,
// SameSite=Lax session cookie and enforces an exact Origin allow-list. Serving
// the SPA and the API from one origin keeps the cookie first-party, removes CORS
// entirely, and means `FRONTEND_URL` on the API is simply this Worker's origin.
//
// `API_ORIGIN` is a plain Worker variable (e.g. https://vbase-api.onrender.com).
// While it is unset the SPA still loads and /api/* returns a clear 503 instead
// of a confusing network error.
// ---------------------------------------------------------------------------

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function json(status, detail) {
  return new Response(JSON.stringify({ detail }), { status, headers: JSON_HEADERS });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      const origin = (env.API_ORIGIN || "").trim();
      if (!origin) {
        return json(503, "API origin is not configured for this deployment.");
      }

      let target;
      try {
        target = new URL(url.pathname + url.search, origin);
      } catch {
        return json(503, "API origin is not a valid absolute URL.");
      }

      // Forward the request unchanged apart from Host: the API sees the same
      // Origin header the browser sent, which is what its allow-list checks.
      const headers = new Headers(request.headers);
      headers.set("host", target.host);
      headers.set("x-forwarded-host", url.host);
      headers.set("x-forwarded-proto", url.protocol.replace(":", ""));

      const init = { method: request.method, headers, redirect: "manual" };
      if (request.method !== "GET" && request.method !== "HEAD") {
        init.body = request.body;
      }

      try {
        return await fetch(new Request(target, init));
      } catch {
        return json(502, "The API backend is unreachable.");
      }
    }

    return env.ASSETS.fetch(request);
  },
};
