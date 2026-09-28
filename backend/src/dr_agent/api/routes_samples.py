"""Sample runbooks and inventories for the dashboard's sample picker.

Only files directly inside `runbooks/`, the upload folder (`RUNBOOK_UPLOAD_DIR`)
and `inventories/` under `API_ALLOWED_DIR` are listed, and reading one goes
through the same allow-list check as `GET /api/v1/dr/analyze` (`api/paths.py`).
`POST /runbooks` saves an uploaded runbook there (design scheduled-analysis 18.2).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from dr_agent.api.body_upload import UploadedRunbook, read_upload
from dr_agent.api.deps import AppState, get_state
from dr_agent.api.openapi import UPLOAD_REQUEST_BODY
from dr_agent.api.paths import resolve_allowed_path
from dr_agent.api.schemas import ErrorBody, SampleFile, SampleList
from dr_agent.loaders import read_text_file
from dr_agent.runbook_uploads import RunbookUploads
from dr_agent.utils.errors import UploadsDisabledError

router = APIRouter(prefix="/api/v1/dr/samples", tags=["samples"])

State = Annotated[AppState, Depends(get_state)]

_RUNBOOK_SUFFIXES = (".md", ".markdown")
_INVENTORY_SUFFIXES = (".json",)


def _list(base: Path, folder: str, suffixes: tuple[str, ...]) -> list[str]:
    directory = base / folder
    if not directory.is_dir():
        return []
    return sorted(
        f"{folder}/{entry.name}"
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix.lower() in suffixes
    )


@router.get("", response_model=SampleList)
async def list_samples(state: State) -> SampleList:
    """Sample runbooks and inventories, as paths relative to `API_ALLOWED_DIR`."""
    base = Path(state.settings.api_allowed_dir).resolve()
    return SampleList(
        runbooks=_list(base, "runbooks", _RUNBOOK_SUFFIXES) + _uploads(state).listed(),
        inventories=_list(base, "inventories", _INVENTORY_SUFFIXES),
    )


@router.get(
    "/file",
    response_model=SampleFile,
    responses={code: {"model": ErrorBody} for code in (403, 404)},
)
async def get_sample(
    state: State,
    path: Annotated[str, Query(min_length=1, max_length=512, examples=["runbooks/x.md"])],
) -> SampleFile:
    """The text of one sample file (a path from `GET /api/v1/dr/samples`)."""
    base = Path(state.settings.api_allowed_dir)
    resolved = resolve_allowed_path(base, path, suffixes=_RUNBOOK_SUFFIXES + _INVENTORY_SUFFIXES)
    return SampleFile(path=path, content=read_text_file(resolved))


@router.post(
    "/runbooks",
    response_model=UploadedRunbook,
    status_code=201,
    openapi_extra=UPLOAD_REQUEST_BODY,
    responses={code: {"model": ErrorBody} for code in (400, 403, 409, 413, 422)},
)
async def upload_runbook(request: Request, state: State) -> UploadedRunbook:
    """Save a runbook (JSON `{fileName, markdown}` or multipart `file`) for analyses and schedules.

    It must parse as a runbook (`422 PARSE_ERROR` otherwise) and is never overwritten:
    a taken name gets `-2`, `-3`, ... `403 UPLOADS_DISABLED` with `RUNBOOK_UPLOADS_ENABLED=false`.
    """
    if not state.settings.runbook_uploads_enabled:
        raise UploadsDisabledError("saving uploaded runbooks is disabled (RUNBOOK_UPLOADS_ENABLED)")
    name, text = await read_upload(request, state.settings.api_max_upload_bytes)
    path, runbook = await asyncio.to_thread(_uploads(state).save, name, text)
    return UploadedRunbook(path=path, service_name=runbook.service_name)


def _uploads(state: AppState) -> RunbookUploads:
    settings = state.settings
    return RunbookUploads(
        Path(settings.api_allowed_dir),
        settings.runbook_upload_dir,
        max_files=settings.runbook_upload_max_files,
    )
