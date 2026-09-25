"""Request-context middleware: request/correlation ids, access log with timing.

Client-supplied `X-Request-ID` / `X-Correlation-ID` are accepted only if they
are short and plain (letters, digits, `.`, `_`, `-`), so they cannot inject
content into logs or headers; otherwise a fresh id is generated. The ids are
bound into structlog context for every log line of the request, including the
analysis job it starts (asyncio tasks copy the context they were created in).

`security_headers_middleware` adds conservative browser hardening headers to
every response. A Content-Security-Policy is set per route where it is safe
(the HTML report export), not globally, because `/docs` loads Swagger UI assets.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from dr_agent.utils.logging import bind_request_context, clear_request_context, get_logger
from dr_agent.utils.timing import Stopwatch

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_log = get_logger("dr_agent.api.access")

CallNext = Callable[[Request], Awaitable[Response]]

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}
# The exported report is self-contained: inline CSS only, no scripts, no remote loads.
REPORT_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _clean_id(value: str | None) -> str | None:
    return value if value is not None and _SAFE_ID.fullmatch(value) else None


async def request_context_middleware(request: Request, call_next: CallNext) -> Response:
    request_id = _clean_id(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex
    correlation_id = _clean_id(request.headers.get(CORRELATION_ID_HEADER)) or request_id
    bind_request_context(request_id, correlation_id)
    watch = Stopwatch()
    try:
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        _log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(watch.stop(), 2),
        )
        return response
    finally:
        clear_request_context()


async def security_headers_middleware(request: Request, call_next: CallNext) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response
