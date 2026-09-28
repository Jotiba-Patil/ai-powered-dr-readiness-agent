"""Reads `POST /api/v1/dr/samples/runbooks` bodies: JSON `{fileName, markdown}` or a multipart
`file`, size-capped like the analyze bodies (`API_MAX_UPLOAD_BYTES` for the runbook text).
"""

from __future__ import annotations

import json

from fastapi import Request
from pydantic import ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from starlette.datastructures import UploadFile

from dr_agent.api.body import check_declared_length, read_limited, read_part, safe_label
from dr_agent.loaders import decode_utf8, error_summary
from dr_agent.models.base import CamelModel
from dr_agent.utils.errors import BadRequestError, PayloadTooLargeError, ValidationError

_OVERHEAD_BYTES = 64 * 1024  # JSON escaping or multipart framing around the runbook text


class UploadRunbookRequest(CamelModel):
    # The runbook is saved exactly as sent, so no whitespace stripping here.
    model_config = ConfigDict(**{**CamelModel.model_config, "str_strip_whitespace": False})

    file_name: str = Field(min_length=1, max_length=255, examples=["my-runbook.md"])
    markdown: str = Field(min_length=1, description="The runbook's Markdown text")


class UploadedRunbook(CamelModel):
    path: str = Field(description="Relative to API_ALLOWED_DIR, e.g. uploads/my-runbook.md")
    service_name: str


async def read_upload(request: Request, max_bytes: int) -> tuple[str, str]:
    """(file name as sent, runbook text)."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    check_declared_length(request, max_bytes + _OVERHEAD_BYTES)
    if content_type == "application/json":
        name, text = _from_json(await read_limited(request, max_bytes + _OVERHEAD_BYTES))
    elif content_type == "multipart/form-data":
        name, text = await _from_multipart(request, max_bytes)
    else:
        raise BadRequestError(
            "Content-Type must be application/json or multipart/form-data",
            details={"received": content_type or None},
        )
    if len(text.encode("utf-8")) > max_bytes:
        raise PayloadTooLargeError("runbook too large", details={"limitBytes": max_bytes})
    return name, text


def _from_json(raw: bytes) -> tuple[str, str]:
    try:
        data: object = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadRequestError("request body is not valid JSON") from exc
    try:
        body = UploadRunbookRequest.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError("invalid upload", details={"errors": error_summary(exc)}) from exc
    return body.file_name, body.markdown


async def _from_multipart(request: Request, max_bytes: int) -> tuple[str, str]:
    async with request.form(max_files=1, max_fields=1, max_part_size=max_bytes) as form:
        part = form.get("file")
        if not isinstance(part, UploadFile):
            raise BadRequestError("multipart body needs a 'file' part")
        name = safe_label(part.filename) or "runbook.md"
        return name, decode_utf8(await read_part(part, max_bytes), label=name)
