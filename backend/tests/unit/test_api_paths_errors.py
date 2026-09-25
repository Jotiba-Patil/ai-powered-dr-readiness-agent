from pathlib import Path

import pytest

from dr_agent.api.errors import json_safe, status_for
from dr_agent.api.paths import resolve_allowed_path
from dr_agent.utils.errors import (
    AnalysisError,
    AppError,
    BadRequestError,
    CapacityError,
    ConfigError,
    ConflictError,
    ExecutionDisabledError,
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


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "allowed" / "runbooks").mkdir(parents=True)
    (tmp_path / "allowed" / "runbooks" / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "secret.md").write_text("# secret", encoding="utf-8")
    return tmp_path / "allowed"


def test_resolves_relative_path_inside_base(base: Path) -> None:
    resolved = resolve_allowed_path(base, "runbooks/a.md", suffixes=(".md",))
    assert resolved == (base / "runbooks" / "a.md").resolve()


@pytest.mark.parametrize("requested", ["../secret.md", "runbooks/../../secret.md"])
def test_traversal_is_rejected(base: Path, requested: str) -> None:
    with pytest.raises(PathNotAllowedError) as info:
        resolve_allowed_path(base, requested, suffixes=(".md",))
    assert str(base) not in info.value.message


def test_absolute_path_is_rejected(base: Path) -> None:
    outside = str((base.parent / "secret.md").resolve())
    with pytest.raises(PathNotAllowedError):
        resolve_allowed_path(base, outside, suffixes=(".md",))


def test_wrong_suffix_is_rejected(base: Path) -> None:
    with pytest.raises(PathNotAllowedError, match=r"\.json"):
        resolve_allowed_path(base, "runbooks/a.md", suffixes=(".json",))


def test_missing_file_is_not_found(base: Path) -> None:
    with pytest.raises(NotFoundError):
        resolve_allowed_path(base, "runbooks/nope.md", suffixes=(".md",))


def test_null_byte_is_rejected(base: Path) -> None:
    with pytest.raises(PathNotAllowedError):
        resolve_allowed_path(base, "runbooks/a\x00.md", suffixes=(".md",))


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (BadRequestError("x"), 400),
        (PathNotAllowedError("x"), 403),
        (NotFoundError("x"), 404),
        (PayloadTooLargeError("x"), 413),
        (ParseError("x"), 422),
        (ValidationError("x"), 422),
        (CapacityError("x"), 429),
        (ConflictError("x"), 409),
        (AnalysisError("x"), 502),
        (ConfigError("x"), 500),
        (ExecutionDisabledError("x"), 403),
        (InvalidTransitionError("x"), 409),
        (StaleCallError("x"), 409),
        (PolicyViolationError("x"), 422),
        (ToolError("x"), 502),
        (AppError("x"), 500),
    ],
)
def test_status_for_maps_error_types(error: AppError, status: int) -> None:
    assert status_for(error) == status


def test_status_for_uses_nearest_mapped_base_class() -> None:
    class CustomParseError(ParseError):
        pass

    assert status_for(CustomParseError("x")) == 422


def test_json_safe_stringifies_unserialisable_values() -> None:
    assert json_safe({"err": ValueError("boom"), "n": 1}) == {"err": "boom", "n": 1}
