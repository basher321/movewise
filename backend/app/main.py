"""FastAPI application. Run (from backend/): uvicorn app.main:app"""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.cookies import ClearCookiesMiddleware
from app.config import get_settings
from app.db.engine import get_engine
from app.errors import error_response, register_error_handlers
from app.notify.worker import run_forever
from app.production import check_production
from app.routers import admin_applications as admin_applications_router
from app.routers import agents as agents_router
from app.routers import imports as imports_router
from app.routers import partners as partners_router
from app.routers import party_documents as party_documents_router
from app.routers import admin_me as admin_me_router
from app.routers import password_reset as password_reset_router
from app.routers import admin_catalog as admin_catalog_router
from app.routers import applications as applications_router
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import catalog as catalog_router
from app.routers import documents as documents_router
from app.routers import enquiries as enquiries_router
from app.routers import enrolments as enrolments_router
from app.routers import certificates as certificates_router
from app.routers import messages as messages_router
from app.routers import finance as finance_router
from app.routers import pay as pay_router
from app.routers import health
from app.routers import licence as licence_router
from app.routers import me as me_router
from app.routers import notifications as notifications_router
from app.routers import settings as settings_router
from app.routers import team as team_router
from app.routers import success as success_router

MAX_BODY_BYTES = 3 * 1024 * 1024
TOO_LARGE_MESSAGE = "Request body is larger than 3 MB."
# B21: an agent or partner document may be up to 10 MB; 1 MB more for the form around it.
DOCUMENT_UPLOAD_PATH = re.compile(r"/api/admin/(agents|partners)/[^/]+/documents")
DOCUMENT_UPLOAD_MAX_BODY = 11 * 1024 * 1024
DOCUMENT_UPLOAD_TOO_LARGE = "The file must be 10 MB or smaller."
# B23: an Excel upload may be up to 5 MB; 1 MB more for the form around it.
EXCEL_IMPORT_PATH = re.compile(r"/api/admin/import/[^/]+/(preview|commit)")
EXCEL_IMPORT_MAX_BODY = 6 * 1024 * 1024
EXCEL_IMPORT_TOO_LARGE = "The file must be 5 MB or smaller."
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Payment gateway callbacks come from the gateway's own site (B07). They change nothing on their
# own: every success is checked with the gateway by the server first.
ORIGIN_EXEMPT_PREFIX = "/api/pay/"


def body_limit(method: str, path: str) -> tuple[int, str]:
    """The largest request body allowed: 3 MB, except an agent or partner document upload (B21)
    and an Excel upload (B23)."""
    if method == "POST" and DOCUMENT_UPLOAD_PATH.fullmatch(path):
        return DOCUMENT_UPLOAD_MAX_BODY, DOCUMENT_UPLOAD_TOO_LARGE
    if method == "POST" and EXCEL_IMPORT_PATH.fullmatch(path):
        return EXCEL_IMPORT_MAX_BODY, EXCEL_IMPORT_TOO_LARGE
    return MAX_BODY_BYTES, TOO_LARGE_MESSAGE


class BodySizeLimitMiddleware:
    """Refuses request bodies over 3 MB (11 MB for an agent or partner document upload)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_body, too_large = body_limit(scope["method"], scope["path"])

        length = Headers(scope=scope).get("content-length")
        if length is not None:
            if not length.isdigit():
                await error_response("VALIDATION", "Invalid Content-Length header.")(scope, receive, send)
                return
            if int(length) > max_body:
                await error_response("VALIDATION", too_large)(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_body:
                    raise HTTPException(status_code=422, detail=too_large)
            return message

        await self.app(scope, limited_receive, send)


class OriginCheckMiddleware:
    """Refuses every request that changes data (not GET, HEAD or OPTIONS) unless its Origin
    header is FRONTEND_ORIGIN: protection against cross-site requests."""

    def __init__(self, app: ASGIApp, allowed_origin: str) -> None:
        self.app = app
        self.allowed_origin = allowed_origin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and not scope["path"].startswith(ORIGIN_EXEMPT_PREFIX)
            and Headers(scope=scope).get("origin") != self.allowed_origin
        ):
            await error_response("FORBIDDEN", "Origin not allowed.")(scope, receive, send)
            return
        await self.app(scope, receive, send)


class JsonCORSMiddleware(CORSMiddleware):
    """CORS where a refused preflight answers with the JSON error format, not plain text."""

    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code != 200:
            return JSONResponse(
                status_code=403,
                content={"code": "FORBIDDEN", "message": "Origin not allowed."},
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """In production, start-up refuses to run unless check_production passes."""
    settings = get_settings()
    if settings.app_env == "production":
        with get_engine().connect() as conn:
            check_production(settings, conn)
    worker: asyncio.Task[None] | None = None
    if settings.notify_worker.strip().lower() != "off":
        worker = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    # API docs only in development; in production /docs, /redoc and /openapi.json are 404.
    dev = settings.app_env == "development"
    app = FastAPI(
        title="Agency Suite API",
        docs_url="/docs" if dev else None,
        redoc_url="/redoc" if dev else None,
        openapi_url="/openapi.json" if dev else None,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.add_middleware(ClearCookiesMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(OriginCheckMiddleware, allowed_origin=settings.frontend_origin)
    app.add_middleware(
        JsonCORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(licence_router.router, prefix="/api")
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(me_router.router, prefix="/api")
    app.include_router(admin_me_router.router, prefix="/api")
    app.include_router(password_reset_router.router, prefix="/api")
    app.include_router(team_router.router, prefix="/api")
    app.include_router(catalog_router.router, prefix="/api")
    app.include_router(success_router.router, prefix="/api")
    app.include_router(admin_catalog_router.router, prefix="/api")
    app.include_router(applications_router.router, prefix="/api")
    app.include_router(admin_applications_router.router, prefix="/api")
    app.include_router(agents_router.router, prefix="/api")
    app.include_router(partners_router.router, prefix="/api")
    app.include_router(party_documents_router.router, prefix="/api")
    app.include_router(imports_router.router, prefix="/api")
    app.include_router(documents_router.router, prefix="/api")
    app.include_router(pay_router.router, prefix="/api")
    app.include_router(finance_router.router, prefix="/api")
    app.include_router(notifications_router.router, prefix="/api")
    app.include_router(enrolments_router.router, prefix="/api")
    app.include_router(certificates_router.router, prefix="/api")
    app.include_router(messages_router.router, prefix="/api")
    app.include_router(enquiries_router.router, prefix="/api")
    app.include_router(audit_router.router, prefix="/api")
    return app


app = create_app()
