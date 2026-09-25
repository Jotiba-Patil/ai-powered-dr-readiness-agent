"""Sample runbooks and inventories for the dashboard's sample picker.

Only files directly inside `runbooks/` and `inventories/` under
`API_ALLOWED_DIR` are listed, and reading one goes through the same
allow-list check as `GET /api/v1/dr/analyze` (`api/paths.py`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from dr_agent.api.deps import AppState, get_state
from dr_agent.api.paths import resolve_allowed_path
from dr_agent.api.schemas import ErrorBody, SampleFile, SampleList
from dr_agent.loaders import read_text_file

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
        runbooks=_list(base, "runbooks", _RUNBOOK_SUFFIXES),
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
