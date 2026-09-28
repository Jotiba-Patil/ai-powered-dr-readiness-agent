"""Where a schedule's runbook and inventory come from (design section 5.4, step 1).

Paths are relative to `API_ALLOWED_DIR` and go through the same allow-list as
`GET /api/v1/dr/analyze`, both when a schedule is saved and on every run, so a
schedule always analyzes the current file and can never reach outside that folder.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dr_agent.api.paths import resolve_allowed_path
from dr_agent.loaders import load_inventory, read_text_file
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.runbook import Runbook
from dr_agent.service import parse_markdown

RUNBOOK_SUFFIXES = (".md", ".markdown")
INVENTORY_SUFFIXES = (".json",)


@dataclass(frozen=True)
class LoadedInput:
    runbook: Runbook
    runbook_label: str
    inventory: SystemInventory | None
    inventory_label: str | None


class RunbookSource(Protocol):
    def check(self, runbook_path: str, inventory_path: str | None) -> None:
        """Raises `PathNotAllowedError` or `NotFoundError` for a path that cannot be used."""
        ...

    async def load(self, runbook_path: str, inventory_path: str | None) -> LoadedInput:
        """Reads and parses the files; raises the same errors as `GET /analyze`."""
        ...


class AllowedDirSource:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def check(self, runbook_path: str, inventory_path: str | None) -> None:
        self._paths(runbook_path, inventory_path)

    async def load(self, runbook_path: str, inventory_path: str | None) -> LoadedInput:
        return await asyncio.to_thread(self._load, runbook_path, inventory_path)

    def _paths(self, runbook_path: str, inventory_path: str | None) -> tuple[Path, Path | None]:
        runbook = resolve_allowed_path(self._base, runbook_path, suffixes=RUNBOOK_SUFFIXES)
        inventory = (
            resolve_allowed_path(self._base, inventory_path, suffixes=INVENTORY_SUFFIXES)
            if inventory_path
            else None
        )
        return runbook, inventory

    def _load(self, runbook_path: str, inventory_path: str | None) -> LoadedInput:
        runbook_file, inventory_file = self._paths(runbook_path, inventory_path)
        return LoadedInput(
            runbook=parse_markdown(read_text_file(runbook_file)),
            runbook_label=runbook_path,
            inventory=load_inventory(inventory_file) if inventory_file else None,
            inventory_label=inventory_path,
        )
