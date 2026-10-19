from __future__ import annotations

import json
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from nexus.core.config import settings
from nexus.core.security import constant_time_equals
from nexus.core.context import build_request_info, reset_request_info, set_request_info

logger = logging.getLogger("nexus.request")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

#: Public marketing endpoint (landing-page contact form) — reachable with no
#: session, so it gets the tightest dedicated bucket.
_CONTACT_PATH = "/api/v1/contact"

#: Endpoints that are reachable before a session exists. They still get the
#: Origin check, but there is no session cookie to double-submit against.
_PRE_AUTH_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    _CONTACT_PATH,
}

#: Endpoints called server-to-server by a provider rather than by a browser.
#: They arrive with no Origin and no CSRF token, so the origin gate has to be
#: skipped — which is only safe because the handler verifies an HMAC over the
#: raw request body before it acts on anything.
_SIGNATURE_VERIFIED_PREFIXES = ("/api/v1/email/webhook/",)

#: Endpoints that verify a credential and therefore get the tight rate limit.
#: Everything else under /api/v1/auth/ (``/auth/me``, ``/auth/sessions``,
#: ``/auth/logout``) is a session probe that the SPA calls on every page load,
#: so it uses the far more generous "session" bucket instead. Putting /auth/me
#: in the credential bucket made a normal navigation burst return 429 and left
#: the app unable to determine whether a session existed.
_CREDENTIAL_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/change-password",
}

#: Fallback ceiling for a bucket that was not explicitly configured.
_DEFAULT_BUCKET_LIMIT = 240


def _normalise_origin(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().rstrip("/")
    if "://" in value:
        scheme, rest = value.split("://", 1)
        host = rest.split("/", 1)[0]
        return f"{scheme.lower()}://{host.lower()}"
    return value.lower()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, emits one structured access log line per request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        token = set_request_info(build_request_info(request))
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                    }
                )
            )
            raise
        finally:
            reset_request_info(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(duration_ms)
        if not request.url.path.startswith(("/health", "/assets")):
            logger.info(
                json.dumps(
                    {
                        "event": "request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": duration_ms,
                        "user_id": getattr(request.state, "user_id", None),
                    }
                )
            )
        return response


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    """Reject unsafe cross-site requests and enforce a CSRF double-submit token.

    Two independent gates, both O(1):

    1. ``Origin`` (falling back to ``Referer``) must match the configured
       allow-list. A request with neither header on an unsafe method is
       rejected, because it cannot be attributed to a trusted browser context.
    2. When a session cookie is present, the ``X-CSRF-Token`` header must equal
       the value of the readable ``vbase_csrf`` cookie that was issued with it.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            request.method in _UNSAFE_METHODS
            and request.url.path.startswith("/api/")
            and not request.url.path.startswith(_SIGNATURE_VERIFIED_PREFIXES)
        ):
            origin = _normalise_origin(request.headers.get("origin")) or _normalise_origin(
                request.headers.get("referer")
            )
            allowed = set(settings.allowed_origins)
            if origin is None:
                return self._reject(request, "Missing Origin/Referer header")
            if origin not in allowed:
                logger.warning("Blocked cross-origin %s %s from %s", request.method, request.url.path, origin)
                return self._reject(request, "Origin not allowed")

            has_session = bool(request.cookies.get(settings.session_cookie_name))
            if has_session and request.url.path not in _PRE_AUTH_PATHS:
                header_token = request.headers.get("x-csrf-token")
                cookie_token = request.cookies.get("vbase_csrf")
                if not header_token or not cookie_token or not constant_time_equals(header_token, cookie_token):
                    logger.warning("CSRF token mismatch on %s %s", request.method, request.url.path)
                    return self._reject(request, "Invalid CSRF token")

        return await call_next(request)

    @staticmethod
    def _reject(request: Request, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": detail, "request_id": getattr(request.state, "request_id", None)},
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client sliding-window rate limit.

    State lives in the process, which is correct for the single-instance free
    tier (Render Free runs one instance). Behind multiple instances each
    process enforces its own window; the limit is then a per-instance ceiling
    rather than a global one.
    """

    def __init__(self, app, limits: dict[str, int] | None = None) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = {}
        # Configured limits win; anything unset falls back to the settings value
        # for that bucket so a partial override in a test stays predictable.
        self._limits = {
            "auth": settings.rate_limit_auth_per_minute,
            "session": settings.rate_limit_session_per_minute,
            "write": settings.rate_limit_write_per_minute,
            "contact": settings.rate_limit_contact_per_minute,
            **(limits or {}),
        }

    def _bucket(self, path: str, method: str) -> str | None:
        if path == _CONTACT_PATH:
            return "contact"
        if path in _CREDENTIAL_PATHS:
            return "auth"
        if method in _UNSAFE_METHODS:
            return "write"
        if path.startswith("/api/v1/auth/"):
            return "session"
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        bucket = self._bucket(request.url.path, request.method)
        if bucket is None:
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for")
        client = (forwarded.split(",")[0].strip() if forwarded else None) or (
            request.client.host if request.client else "unknown"
        )
        key = f"{bucket}:{client}"
        limit = self._limits.get(bucket, _DEFAULT_BUCKET_LIMIT)
        now = time.monotonic()
        window = self._hits.setdefault(key, deque())

        while window and now - window[0] > 60:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, int(60 - (now - window[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded for {bucket} requests"},
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        # Opportunistic cleanup so the dict cannot grow without bound.
        if len(self._hits) > 4096:
            for stale in [k for k, v in self._hits.items() if not v]:
                self._hits.pop(stale, None)

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defensive response headers for a JSON API."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
