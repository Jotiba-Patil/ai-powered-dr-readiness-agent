"""Reads `POST /api/v1/dr/analyze` bodies: JSON or multipart, size-capped.

The route accepts two content types on one path (per the brief), so the body is
read here by hand rather than through a FastAPI body parameter. JSON bodies are
streamed and cut off at the byte limit; multipart uploads are checked against
the declared Content-Length first and then per file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PureWindowsPath

from fastapi import Request
from pydantic import ValidationError as PydanticValidationError
from starlette.datastructures import UploadFile

from dr_agent.api.schemas import AnalyzeJsonRequest
from dr_agent.loaders import decode_utf8, error_summary, inventory_from_text
from dr_agent.models.inventory import SystemInventory
from dr_agent.utils.errors import BadRequestError, PayloadTooLargeError, ValidationError

_MULTIPART_OVERHEAD_BYTES = 64 * 1024
_DEFAULT_RUNBOOK_LABEL = "request-body.md"


@dataclass(frozen=True)
class AnalyzeInput:
    runbook_markdown: str
    inventory: SystemInventory | None
    runbook_label: str
    inventory_label: str | None


async def read_analyze_input(request: Request, max_bytes: int) -> AnalyzeInput:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        _check_declared_length(request, max_bytes)
        return _from_json(await _read_limited(request, max_bytes))
    if content_type.startswith("multipart/form-data"):
        _check_declared_length(request, 2 * max_bytes + _MULTIPART_OVERHEAD_BYTES)
        return await _from_multipart(request, max_bytes)
    raise BadRequestError(
        "Content-Type must be application/json or multipart/form-data",
        details={"received": content_type or None},
    )


def _check_declared_length(request: Request, limit: int) -> None:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError(
            "request body too large", details={"limitBytes": limit, "declaredBytes": int(declared)}
        )


async def _read_limited(request: Request, max_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise PayloadTooLargeError("request body too large", details={"limitBytes": max_bytes})
    return bytes(body)


def _from_json(raw: bytes) -> AnalyzeInput:
    try:
        data: object = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadRequestError("request body is not valid JSON") from exc
    try:
        parsed = AnalyzeJsonRequest.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(
            "invalid analyze request", details={"errors": error_summary(exc)}
        ) from exc
    return AnalyzeInput(
        runbook_markdown=parsed.runbook_markdown,
        inventory=parsed.inventory,
        runbook_label=safe_label(parsed.runbook_name) or _DEFAULT_RUNBOOK_LABEL,
        inventory_label="request-body.json" if parsed.inventory else None,
    )


async def _from_multipart(request: Request, max_bytes: int) -> AnalyzeInput:
    async with request.form(max_files=2, max_fields=2, max_part_size=max_bytes) as form:
        runbook_part = form.get("runbook")
        inventory_part = form.get("inventory")
        if not isinstance(runbook_part, UploadFile):
            raise BadRequestError("multipart body needs a 'runbook' file part")
        runbook_label = safe_label(runbook_part.filename) or "runbook.md"
        markdown = decode_utf8(await _read_part(runbook_part, max_bytes), label=runbook_label)

        if inventory_part is None:
            return AnalyzeInput(markdown, None, runbook_label, None)
        if not isinstance(inventory_part, UploadFile):
            raise BadRequestError("'inventory' must be a file part")
        inventory_label = safe_label(inventory_part.filename) or "inventory.json"
        text = decode_utf8(await _read_part(inventory_part, max_bytes), label=inventory_label)
        inventory = inventory_from_text(text, label=inventory_label)
    return AnalyzeInput(markdown, inventory, runbook_label, inventory_label)


async def _read_part(part: UploadFile, max_bytes: int) -> bytes:
    data = await part.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"uploaded file {part.filename!r} too large", details={"limitBytes": max_bytes}
        )
    return data


def safe_label(name: str | None) -> str | None:
    """Keep only a client-supplied file name's last component (no directories)."""
    if not name:
        return None
    return PureWindowsPath(name).name[:255] or None
