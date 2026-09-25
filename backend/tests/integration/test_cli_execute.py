"""`dr-agent execute` end to end: real settings, the mock MCP server over stdio, typed answers."""

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import MOCK, REPO
from dr_agent import cli

RUNBOOK = str(MOCK / "runbooks" / "estimate-service-executable.md")
INVENTORY = str(MOCK / "inventories" / "healthy.json")
ANSWERS = ["Ann", "ok", "dashboard", "Ann", "Ann", "Ben", "Ann", "Ann", "Ben"]
runner = CliRunner()


@pytest.fixture
def execution_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    servers = tmp_path / "mcp-servers.json"
    servers.write_text(
        json.dumps(
            {
                "drsim": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-m", "dr_agent.mock_mcp"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)  # no .env from the repository
    for name, value in {
        "LLM_PROVIDER": "none",
        "EXECUTION_ENABLED": "true",
        "EXECUTION_ALLOW_LIVE": "true",
        "EXECUTION_DB_PATH": str(tmp_path / "executions.db"),
        "MCP_SERVERS_FILE": str(servers),
        "EXECUTION_POLICY_FILE": str(REPO / "execution-policy.json"),
    }.items():
        monkeypatch.setenv(name, value)
    return tmp_path


def test_live_run_completes_with_exit_0(execution_env: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["execute", "-r", RUNBOOK, "--operator", "Olivia", "--live", "-i", INVENTORY],
        input="y\n" + "\n".join(ANSWERS) + "\n",
    )
    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())  # Rich wraps long lines
    assert "Readiness: risk 0 (LOW); RTO feasible (55 of 60 min)" in output
    assert "(live) for estimate-service-executable.md" in output
    assert "COMPLETED; audit chain valid" in output


def test_abort_exits_2(execution_env: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["execute", "-r", RUNBOOK, "--operator", "Olivia"],
        input="y\nabort\nwrong runbook\n",
    )
    assert result.exit_code == 2, result.output
    assert "(dry_run)" in result.output
    assert "ABORTED" in result.output


def test_declining_after_the_analysis_executes_nothing(execution_env: Path) -> None:
    result = runner.invoke(cli.app, ["execute", "-r", RUNBOOK, "--operator", "Olivia"], input="n\n")
    assert result.exit_code == 0, result.output
    assert "Readiness: risk" in result.output
    assert "Not executed." in result.output
    assert _executions(execution_env) == []


def test_disabled_execution_is_an_error(
    execution_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    result = runner.invoke(cli.app, ["execute", "-r", RUNBOOK, "--operator", "Olivia"])
    assert result.exit_code == 1
    assert "EXECUTION_DISABLED" in result.output
    assert "Readiness" not in result.output  # refused before spending time on the analysis


def _executions(tmp_path: Path) -> list[tuple[str, str | None]]:
    with sqlite3.connect(tmp_path / "dr-agent.db") as conn:
        return conn.execute("SELECT id, analysis_id FROM executions").fetchall()


def _stored_analysis_id() -> str:
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-f", "json"])
    match = re.search(r"Saved to history as ([0-9a-f]{32})", result.stderr)
    assert match, result.output
    return match.group(1)


def test_execute_a_stored_analysis(execution_env: Path) -> None:
    analysis_id = _stored_analysis_id()
    result = runner.invoke(
        cli.app,
        ["execute", "--analysis", analysis_id, "--operator", "Olivia", "--live"],
        input="y\n" + "\n".join(ANSWERS) + "\n",
    )
    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())
    assert f"Analysis {analysis_id} (stored in the history)" in output
    assert "COMPLETED; audit chain valid" in output
    assert [link for _, link in _executions(execution_env)] == [analysis_id]


def test_execute_runbook_links_its_new_analysis(execution_env: Path) -> None:
    result = runner.invoke(
        cli.app, ["execute", "-r", RUNBOOK, "--operator", "Olivia"], input="y\nabort\nx\n"
    )
    assert result.exit_code == 2, result.output
    ((_, link),) = _executions(execution_env)
    assert link is not None
    assert link in result.output


def test_execute_needs_exactly_one_source(execution_env: Path) -> None:
    both = ["execute", "-r", RUNBOOK, "--analysis", "a1", "--operator", "Olivia"]
    assert cli.main(both) == 1
    assert cli.main(["execute", "--operator", "Olivia"]) == 1
    missing = runner.invoke(cli.app, ["execute", "--analysis", "nope", "--operator", "Olivia"])
    assert missing.exit_code == 1
    assert "NOT_FOUND" in missing.output
