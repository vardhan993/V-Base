from __future__ import annotations

import contextvars
from dataclasses import dataclass

from starlette.requests import Request

#: Set once per request by RequestContextMiddleware. Using a ContextVar keeps
#: the value correct per-task under asyncio without threading a Request object
#: through every service function.
_current: contextvars.ContextVar[RequestInfo | None] = contextvars.ContextVar("vbase_request_info", default=None)


@dataclass(frozen=True, slots=True)
class RequestInfo:
    request_id: str | None
    ip_address: str | None
    user_agent: str | None


def set_request_info(info: RequestInfo | None) -> contextvars.Token:
    return _current.set(info)


def reset_request_info(token: contextvars.Token) -> None:
    _current.reset(token)


def request_info() -> RequestInfo | None:
    return _current.get()


def build_request_info(request: Request) -> RequestInfo:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = None
    return RequestInfo(
        request_id=getattr(request.state, "request_id", None),
        ip_address=client_ip[:45] if client_ip else None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
