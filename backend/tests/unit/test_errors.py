import pytest

from dr_agent.utils.errors import (
    AnalysisError,
    AppError,
    ConfigError,
    ExecutionDisabledError,
    InvalidTransitionError,
    ParseError,
    PolicyViolationError,
    StaleCallError,
    ToolError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (ParseError, "PARSE_ERROR"),
        (ValidationError, "VALIDATION_ERROR"),
        (AnalysisError, "ANALYSIS_ERROR"),
        (ConfigError, "CONFIG_ERROR"),
        (ExecutionDisabledError, "EXECUTION_DISABLED"),
        (InvalidTransitionError, "INVALID_TRANSITION"),
        (StaleCallError, "STALE_CALL"),
        (PolicyViolationError, "POLICY_VIOLATION"),
        (ToolError, "TOOL_ERROR"),
    ],
)
def test_subclasses_have_stable_codes(cls: type[AppError], code: str) -> None:
    err = cls("boom")
    assert isinstance(err, AppError)
    assert err.code == code
    assert str(err) == "boom"


def test_to_dict_without_details() -> None:
    assert ParseError("bad").to_dict() == {"error": "bad", "code": "PARSE_ERROR"}


def test_to_dict_with_details() -> None:
    err = ValidationError("bad", details={"field": "rto"})
    assert err.to_dict() == {
        "error": "bad",
        "code": "VALIDATION_ERROR",
        "details": {"field": "rto"},
    }
