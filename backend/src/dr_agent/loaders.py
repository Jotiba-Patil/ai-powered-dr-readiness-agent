"""Boundary loaders: files and raw payloads -> validated models or typed errors.

Shared by the CLI (local paths) and the API (uploads, JSON bodies and
allow-listed server paths), so both reject bad input with the same error codes.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from dr_agent.models.inventory import SystemInventory
from dr_agent.utils.errors import BadRequestError, NotFoundError, ValidationError


def read_text_file(path: Path) -> str:
    """Read a UTF-8 text file, mapping I/O and encoding problems to typed errors."""
    if not path.is_file():
        raise NotFoundError(f"file not found: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError(f"{path.name} is not valid UTF-8 text") from exc
    except OSError as exc:
        # No str(exc) in details: it embeds the absolute server path.
        raise NotFoundError(f"could not read {path.name}") from exc


def decode_utf8(raw: bytes, *, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError(f"{label} is not valid UTF-8 text") from exc


def inventory_from_text(text: str, *, label: str) -> SystemInventory:
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{label} is not valid JSON",
            details={"line": exc.lineno, "column": exc.colno, "reason": exc.msg},
        ) from exc
    return inventory_from_data(data, label=label)


def inventory_from_data(data: object, *, label: str) -> SystemInventory:
    try:
        return SystemInventory.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(
            f"{label} is not a valid inventory", details={"errors": error_summary(exc)}
        ) from exc


def error_summary(exc: PydanticValidationError) -> list[dict[str, object]]:
    """Location, message and type only: the offending `input` may be large, untrusted text."""
    return [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]


def load_inventory(path: Path) -> SystemInventory:
    return inventory_from_text(read_text_file(path), label=path.name)
