"""structlog setup: JSON logs, request/correlation ids, secret redaction."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, MutableMapping
from typing import TextIO, cast

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

_SENSITIVE_PARTS = ("api_key", "apikey", "secret", "password", "token", "authorization")
REDACTED = "***"
# `scheme://user:password@host` -> `scheme://***@host` (httpx errors quote the full URL).
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@")


def scrub_url_credentials(text: str) -> str:
    """Remove the user-info part of every URL in `text`."""
    return _URL_CREDENTIALS.sub(rf"\g<scheme>{REDACTED}@", text)


def redact_secrets(
    _logger: WrappedLogger, _method: str, event_dict: MutableMapping[str, object]
) -> EventDict:
    """Replace values of keys that look like secrets and strip credentials from URLs."""
    for key, value in event_dict.items():
        if any(part in key.lower() for part in _SENSITIVE_PARTS):
            event_dict[key] = REDACTED
        elif isinstance(value, str):
            event_dict[key] = scrub_url_credentials(value)
    return dict(event_dict)


def configure_logging(level: str = "info", *, stream: TextIO | None = None) -> None:
    """Configure structlog once at startup. `level` is a standard level name.

    `stream` defaults to stdout; the CLI passes stderr so stdout stays clean for
    piping reports (`dr-agent analyze --format json > report.json`).
    """
    numeric = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            redact_secrets,  # after format_exc_info so tracebacks are scrubbed too
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    return cast(FilteringBoundLogger, structlog.get_logger(name))


def bind_request_context(request_id: str, correlation_id: str | None = None) -> None:
    """Attach ids to every log line emitted in the current context."""
    bind_contextvars(request_id=request_id, correlation_id=correlation_id or request_id)


def clear_request_context() -> None:
    clear_contextvars()


def current_context() -> Mapping[str, object]:
    return structlog.contextvars.get_contextvars()
