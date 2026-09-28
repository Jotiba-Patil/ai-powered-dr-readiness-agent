"""Saved runbook uploads (design scheduled-analysis section 18.2); framework-free.

Files go to one folder inside `API_ALLOWED_DIR` and are never overwritten: the
name is reduced to `[a-z0-9-]`, a taken name gets `-2`, `-3`, ..., the name is
reserved with an exclusive create, and the text is written to a temporary file
and moved over that placeholder. Only text that parses as a runbook is saved,
so a schedule can never point at a file that cannot run.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path

from dr_agent.models.runbook import Runbook
from dr_agent.service import parse_markdown
from dr_agent.utils.errors import BadRequestError, ConfigError, ConflictError
from dr_agent.utils.logging import get_logger

SUFFIXES = (".md", ".markdown")
MAX_NAME = 60
_UNSAFE = re.compile(r"[^a-z0-9]+")
_log = get_logger("dr_agent.uploads")


class RunbookUploads:
    def __init__(self, base_dir: Path, folder: str, *, max_files: int) -> None:
        self._base = base_dir.resolve()
        self._folder = folder
        self._max_files = max_files

    @property
    def directory(self) -> Path:
        """The upload folder; `ConfigError` if it would lie outside `API_ALLOWED_DIR`."""
        directory = (self._base / self._folder).resolve()
        if not directory.is_relative_to(self._base) or directory == self._base:
            raise ConfigError("RUNBOOK_UPLOAD_DIR must be a folder inside API_ALLOWED_DIR")
        return directory

    def listed(self) -> list[str]:
        """Saved runbooks as paths relative to `API_ALLOWED_DIR`, e.g. `uploads/x.md`."""
        directory = self.directory
        if not directory.is_dir():
            return []
        return sorted(
            f"{self._folder}/{entry.name}"
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() in SUFFIXES
        )

    def save(self, file_name: str, markdown: str) -> tuple[str, Runbook]:
        """Checks and saves; returns the path relative to `API_ALLOWED_DIR` and the runbook."""
        if Path(file_name).suffix.lower() not in SUFFIXES:
            raise BadRequestError("only Markdown runbooks (.md, .markdown) can be uploaded")
        runbook = parse_markdown(markdown)  # ParseError: not saved
        directory = self.directory
        directory.mkdir(parents=True, exist_ok=True)
        if len(self.listed()) >= self._max_files:
            raise ConflictError("too many uploaded runbooks", details={"maxFiles": self._max_files})
        target = _reserve(directory, safe_stem(file_name))
        _write_over(target, markdown)
        _log.info("runbook_uploaded", path=f"{self._folder}/{target.name}", bytes=len(markdown))
        return f"{self._folder}/{target.name}", runbook


def safe_stem(file_name: str) -> str:
    """`../My Runbook (v2).md` -> `my-runbook-v2`; empty names become `runbook`."""
    stem = Path(file_name.replace("\\", "/")).name
    stem = stem[: -len(Path(stem).suffix)] if Path(stem).suffix else stem
    cleaned = _UNSAFE.sub("-", stem.casefold()).strip("-")[:MAX_NAME].strip("-")
    return cleaned or "runbook"


def _reserve(directory: Path, stem: str) -> Path:
    """Claims the first free `<stem>.md`, `<stem>-2.md`, ... with an exclusive create."""
    for number in range(1, 1000):
        name = f"{stem}.md" if number == 1 else f"{stem}-{number}.md"
        target = directory / name
        try:
            with target.open("x", encoding="utf-8"):
                return target
        except FileExistsError:
            continue
    raise ConflictError(f"no free file name for {stem!r}")


def _write_over(target: Path, text: str) -> None:
    """Writes to a temporary file in the same folder, then moves it over the placeholder."""
    handle, temp = tempfile.mkstemp(dir=target.parent, prefix=".upload-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        os.replace(temp, target)
    except OSError:
        with contextlib.suppress(OSError):
            Path(temp).unlink()
        with contextlib.suppress(OSError):
            target.unlink()
        raise
