"""Shared error format: every error is JSON {"code": ..., "message": ...}.

Codes and statuses match specs/F02_api_contract_mock.md, plus INTERNAL 500.
"""

import logging
from typing import Literal, TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app")

ErrorCode = Literal[
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "MODULE_NOT_LICENSED",
    "NOT_FOUND",
    "CONFLICT",
    "VALIDATION",
    "EXPIRED",
    "TOO_MANY_TRIES",
    "INTERNAL",
]

STATUS_BY_CODE: dict[ErrorCode, int] = {
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "MODULE_NOT_LICENSED": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "VALIDATION": 422,
    "EXPIRED": 410,
    "TOO_MANY_TRIES": 429,
    "INTERNAL": 500,
}

_CODE_BY_HTTP_STATUS: dict[int, ErrorCode] = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "NOT_FOUND",
    409: "CONFLICT",
    410: "EXPIRED",
    422: "VALIDATION",
    429: "TOO_MANY_TRIES",
}

INTERNAL_MESSAGE = "Something went wrong."


class ApiError(Exception):
    def __init__(self, code: ErrorCode, status: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


M = TypeVar("M", bound=BaseModel)


def parse_body(model: type[M], raw: bytes) -> M:
    """Parse a JSON body inside the endpoint, after the sign-in and role checks have run."""
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None


def error_response(code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=STATUS_BY_CODE[code], content={"code": code, "message": message})


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    if first.get("type") == "json_invalid":
        return "Request body is not valid JSON."
    field = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    msg = str(first.get("msg", "Invalid value"))
    return f"{field}: {msg}" if field else msg


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status, content={"code": exc.code, "message": exc.message})


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response("VALIDATION", _validation_message(exc))


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code >= 500:
        return error_response("INTERNAL", INTERNAL_MESSAGE)
    code = _CODE_BY_HTTP_STATUS.get(exc.status_code, "VALIDATION")
    if code == "NOT_FOUND":
        return error_response(code, "Not found.")
    message = exc.detail if isinstance(exc.detail, str) else "Invalid request."
    return error_response(code, message)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response("INTERNAL", INTERNAL_MESSAGE)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
