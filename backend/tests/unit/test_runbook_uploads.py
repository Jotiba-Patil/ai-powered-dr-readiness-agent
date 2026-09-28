"""Saved runbook uploads: names, no overwrite, parse check, limits, folder containment."""

from __future__ import annotations

from pathlib import Path

import pytest
from history_support import MOCK

from dr_agent.runbook_uploads import RunbookUploads, safe_stem
from dr_agent.utils.errors import BadRequestError, ConfigError, ConflictError, ParseError

RUNBOOK = (MOCK / "runbooks" / "estimate-service.md").read_text(encoding="utf-8")


def uploads(tmp_path: Path, **kwargs: int) -> RunbookUploads:
    return RunbookUploads(tmp_path, "uploads", max_files=kwargs.get("max_files", 10))


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("estimate-service.md", "estimate-service"),
        ("My Runbook (v2).markdown", "my-runbook-v2"),
        ("../../etc/passwd.md", "passwd"),
        ("C:\\temp\\Plan.MD", "plan"),
        ("...md", "runbook"),
        ("ünïcödé.md", "n-c-d"),
        ("x" * 80 + ".md", "x" * 60),
    ],
)
def test_safe_stem(name: str, stem: str) -> None:
    assert safe_stem(name) == stem


def test_saved_listed_and_never_overwritten(tmp_path: Path) -> None:
    store = uploads(tmp_path)
    assert store.listed() == []
    first, runbook = store.save("Estimate Service.md", RUNBOOK)
    second, _ = store.save("estimate-service.md", RUNBOOK.replace("Estimate", "Other"))
    third, _ = store.save("estimate-service.md", RUNBOOK)
    assert (first, second, third) == (
        "uploads/estimate-service.md",
        "uploads/estimate-service-2.md",
        "uploads/estimate-service-3.md",
    )
    assert runbook.service_name == "Estimate Service"
    assert (tmp_path / "uploads" / "estimate-service.md").read_text(encoding="utf-8") == RUNBOOK
    assert "Other" in (tmp_path / "uploads" / "estimate-service-2.md").read_text(encoding="utf-8")
    assert store.listed() == sorted([first, second, third])  # alphabetical, like the samples
    assert not list((tmp_path / "uploads").glob(".upload-*"))  # no temporary files left


def test_only_runbooks_are_saved(tmp_path: Path) -> None:
    store = uploads(tmp_path)
    with pytest.raises(BadRequestError, match="Markdown"):
        store.save("inventory.json", RUNBOOK)
    with pytest.raises(ParseError):
        store.save("notes.md", "just some notes, no runbook structure")
    assert not (tmp_path / "uploads").exists() or store.listed() == []


def test_file_count_limit(tmp_path: Path) -> None:
    store = uploads(tmp_path, max_files=1)
    store.save("a.md", RUNBOOK)
    with pytest.raises(ConflictError, match="too many"):
        store.save("b.md", RUNBOOK)


@pytest.mark.parametrize("folder", ["..", "../outside", "."])
def test_folder_must_stay_inside_the_allowed_dir(tmp_path: Path, folder: str) -> None:
    with pytest.raises(ConfigError):
        RunbookUploads(tmp_path / "base", folder, max_files=5).save("a.md", RUNBOOK)
