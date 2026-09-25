"""Global error handling: every failure leaves the API as `{error, code, details?}`."""

from __future__ import annotations

import json
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dr_agent.utils.errors import (
    AnalysisError,
    AppError,
    BadRequestError,
    CapacityError,
    ConfigError,
    ConflictError,
    ExecutionDisabledError,
    HistoryDisabledError,
    InvalidTransitionError,
    NotFoundError,
    ParseError,
    PathNotAllowedError,
    PayloadTooLargeError,
    PolicyViolationError,
    StaleCallError,
    ToolError,
    ValidationError,
)
from dr_agent.utils.logging import get_logger

_STATUS_BY_ERROR: dict[type[AppError], int] = {
    BadRequestError: 400,
    PathNotAllowedError: 403,
    ExecutionDisabledError: 403,
    HistoryDisabledError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidTransitionError: 409,
    StaleCallError: 409,
    PolicyViolationError: 422,
    PayloadTooLargeError: 413,
    ParseError: 422,
    ValidationError: 422,
    CapacityError: 429,
    AnalysisError: 502,
    ToolError: 502,
    ConfigError: 500,
}
_log = get_logger("dr_agent.api.errors")


def status_for(exc: AppError) -> int:
    for cls in type(exc).__mro__:
        if cls in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[cls]
    return 500


def json_safe(value: object) -> object:
    """Round-trip through JSON so error details (which may hold exceptions) always serialize."""
    return json.loads(json.dumps(value, default=str))


def error_response(status: int, error: str, code: str, details: object = None) -> JSONResponse:
    body: dict[str, object] = {"error": error, "code": code}
    if details:
        body["details"] = json_safe(details)
    return JSONResponse(body, status_code=status)


async def _app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 -- registered for AppError only
    return error_response(status_for(exc), exc.message, exc.code, exc.details)


async def _request_validation(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 -- registered for this type only
    errors = [{k: v for k, v in err.items() if k in {"loc", "msg", "type"}} for err in exc.errors()]
    return error_response(422, "request validation failed", "VALIDATION_ERROR", {"errors": errors})


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 -- registered for this type only
    code = HTTPStatus(exc.status_code).name if exc.status_code in HTTPStatus else "HTTP_ERROR"
    return error_response(exc.status_code, str(exc.detail), code)


async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    _log.error("unhandled_error", error_type=type(exc).__name__, exc_info=exc)
    return error_response(500, "internal server error", "INTERNAL_ERROR")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _request_validation)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
