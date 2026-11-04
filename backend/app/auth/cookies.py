"""Session cookies: mw_admin and mw_app_<module>, each holding a random token.

A dependency that finds a cookie no longer valid calls clear_later(); ClearCookiesMiddleware
then adds the clearing Set-Cookie header to the response, error responses included.
"""

from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.licence import Module

ADMIN_COOKIE = "mw_admin"
COOKIE_PATH = "/api"
_STATE_KEY = "mw_clear_cookies"


def applicant_cookie(module: Module) -> str:
    return f"mw_app_{module}"


def _secure() -> bool:
    return get_settings().app_env == "production"


def _pending(scope: Scope) -> set[str]:
    state = scope.setdefault("state", {})
    pending = state.get(_STATE_KEY)
    if pending is None:
        pending = state[_STATE_KEY] = set()
    return pending


def set_session_cookie(request: Request, response: Response, name: str, token: str, max_age: int) -> None:
    _pending(request.scope).discard(name)
    response.set_cookie(
        name,
        token,
        max_age=max_age,
        path=COOKIE_PATH,
        secure=_secure(),
        httponly=True,
        samesite="lax",
    )


def clear_later(request: Request, name: str) -> None:
    _pending(request.scope).add(name)


def _clear_header(name: str) -> bytes:
    response = Response()
    response.delete_cookie(name, path=COOKIE_PATH, secure=_secure(), httponly=True, samesite="lax")
    return next(value for key, value in response.raw_headers if key == b"set-cookie")


class ClearCookiesMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        pending = _pending(scope)

        async def send_with_clearing(message: Message) -> None:
            if message["type"] == "http.response.start" and pending:
                headers = MutableHeaders(scope=message)
                for name in sorted(pending):
                    headers.append("set-cookie", _clear_header(name).decode("latin-1"))
            await send(message)

        await self.app(scope, receive, send_with_clearing)
