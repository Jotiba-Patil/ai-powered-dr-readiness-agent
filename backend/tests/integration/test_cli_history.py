"""`dr-agent analyze` stores analyses; `dr-agent history list|show|delete` reads them back."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import MOCK
from dr_agent import cli

RUNBOOK = str(MOCK / "runbooks" / "estimate-service.md")
INVENTORY = str(MOCK / "inventories" / "healthy.json")
runner = CliRunner()


@pytest.fixture(autouse=True)
def rules_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env from the repository
    monkeypatch.setenv("LLM_PROVIDER", "none")


def _analyze(*extra: str) -> str:
    result = runner.invoke(
        cli.app, ["analyze", "-r", RUNBOOK, "-i", INVENTORY, "-f", "json", *extra]
    )
    assert result.exit_code == 0, result.output
    return result.stderr


def _saved_id(stderr: str) -> str:
    match = re.search(r"Saved to history as ([0-9a-f]{32})", stderr)
    assert match, stderr
    return match.group(1)


def test_analyze_saves_and_history_reads_it_back() -> None:
    analysis_id = _saved_id(_analyze())
    listed = runner.invoke(cli.app, ["history", "list"])
    assert listed.exit_code == 0, listed.output
    flat = " ".join(listed.output.split())
    assert analysis_id in flat
    assert "Estimate Service" in flat
    shown = runner.invoke(cli.app, ["history", "show", analysis_id, "-f", "json"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["serviceSummary"]["name"] == "Estimate Service"
    markdown = runner.invoke(cli.app, ["history", "show", analysis_id, "--runbook"])
    assert markdown.stdout.strip() == Path(RUNBOOK).read_text("utf-8").strip()


def test_show_writes_to_a_file(tmp_path: Path) -> None:
    analysis_id = _saved_id(_analyze())
    target = tmp_path / "report.html"
    shown = runner.invoke(
        cli.app, ["history", "show", analysis_id, "-f", "html", "-o", str(target)]
    )
    assert shown.exit_code == 0, shown.output
    assert "<html" in target.read_text("utf-8").lower()


def test_no_save_and_empty_history() -> None:
    assert "Saved to history" not in _analyze("--no-save")
    listed = runner.invoke(cli.app, ["history", "list"])
    assert "No stored analyses." in listed.output


def test_delete_asks_and_unknown_ids_fail() -> None:
    analysis_id = _saved_id(_analyze())
    kept = runner.invoke(cli.app, ["history", "delete", analysis_id], input="n\n")
    assert "Not deleted." in kept.output
    deleted = runner.invoke(cli.app, ["history", "delete", analysis_id, "--yes"])
    assert deleted.exit_code == 0, deleted.output
    missing = runner.invoke(cli.app, ["history", "show", analysis_id])
    assert missing.exit_code == 1
    assert json.loads(missing.stderr)["code"] == "NOT_FOUND"


def test_history_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HISTORY_ENABLED", "false")
    assert "Saved to history" not in _analyze()
    refused = runner.invoke(cli.app, ["history", "list"])
    assert refused.exit_code == 1
    assert json.loads(refused.stderr)["code"] == "HISTORY_DISABLED"
