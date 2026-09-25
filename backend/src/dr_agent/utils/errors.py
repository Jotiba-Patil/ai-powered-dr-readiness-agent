"""Typed error hierarchy. Every error carries a stable machine-readable `code`."""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application errors."""

    code: str = "APP_ERROR"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, object]:
        """Shared error shape used by the CLI and API: {error, code, details?}."""
        body: dict[str, object] = {"error": self.message, "code": self.code}
        if self.details:
            body["details"] = self.details
        return body


class ParseError(AppError):
    """A runbook could not be parsed into a valid model."""

    code = "PARSE_ERROR"


class ValidationError(AppError):
    """External input (inventory, API body, health result) failed validation."""

    code = "VALIDATION_ERROR"


class AnalysisError(AppError):
    """The analysis pipeline (including LLM output validation) failed."""

    code = "ANALYSIS_ERROR"


class ConfigError(AppError):
    """Configuration is missing or invalid."""

    code = "CONFIG_ERROR"


class BadRequestError(AppError):
    """The request itself is malformed (wrong content type, bad encoding, missing part)."""

    code = "BAD_REQUEST"


class PathNotAllowedError(AppError):
    """A server-side file path resolves outside the allow-listed directory."""

    code = "PATH_NOT_ALLOWED"


class NotFoundError(AppError):
    """A requested resource (file, job) does not exist."""

    code = "NOT_FOUND"


class PayloadTooLargeError(AppError):
    """An upload or request body exceeds the configured size limit."""

    code = "PAYLOAD_TOO_LARGE"


class CapacityError(AppError):
    """Too much queued work (e.g. unfinished analysis jobs); retry later."""

    code = "CAPACITY_EXCEEDED"


class ConflictError(AppError):
    """The resource is not in a state that allows the request (e.g. exporting an unfinished job)."""

    code = "CONFLICT"


class ExecutionDisabledError(AppError):
    """Execution is switched off (`EXECUTION_ENABLED`), or live mode is not allowed."""

    code = "EXECUTION_DISABLED"


class HistoryDisabledError(AppError):
    """Analysis history is switched off (`HISTORY_ENABLED=false`)."""

    code = "HISTORY_DISABLED"


class InvalidTransitionError(AppError):
    """A step or execution cannot move from its current state on the requested event."""

    code = "INVALID_TRANSITION"


class StaleCallError(AppError):
    """An approval was given for a call that has changed since it was shown."""

    code = "STALE_CALL"


class PolicyViolationError(AppError):
    """A tool call is not allow-listed, has invalid arguments, or breaks an approval rule."""

    code = "POLICY_VIOLATION"


class ToolError(AppError):
    """A tool call could not be completed (transport failure, timeout, server error)."""

    code = "TOOL_ERROR"
