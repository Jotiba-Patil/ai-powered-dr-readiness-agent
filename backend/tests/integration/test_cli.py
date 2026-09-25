"""CLI tests via Typer's CliRunner with injected fakes (no model, no network, no sleeps)."""

import json
from pathlib import Path

import pytest
import typer
from conftest import MOCK, REPO, fake_llm, mock_checker
from typer.testing import CliRunner

from dr_agent import __version__, cli

RUNBOOK = str(MOCK / "runbooks" / "estimate-service.md")
INVENTORY = str(MOCK / "inventories" / "healthy.json")
runner = CliRunner()


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Inject a FakeProvider (risk 42 unless overridden) and a no-sleep mock checker."""
    seen: dict[str, object] = {"risk": 42}
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LOG_LEVEL", "info")

    def build_llm(*_args: object) -> object:
        return fake_llm(risk_score=int(str(seen["risk"])))

    def build_checker(*_args: object, chaos: bool | None = None) -> object:
        seen["chaos"] = chaos
        return mock_checker()

    monkeypatch.setattr(cli, "build_llm", build_llm)
    monkeypatch.setattr(cli, "build_checker", build_checker)
    return seen


def test_version() -> None:
    result = runner.invoke(cli.app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"dr-agent {__version__}"


def test_analyze_terminal_output_exit_0() -> None:
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-i", INVENTORY])
    assert result.exit_code == 0
    assert "Estimate Service readiness report" in result.stdout
    assert "Risk score: 42/100" in result.stdout


def test_analyze_json_is_clean_stdout_and_critical_exits_2(fakes: dict[str, object]) -> None:
    fakes["risk"] = 95
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-i", INVENTORY, "-f", "json", "-v"])
    assert result.exit_code == cli.EXIT_CRITICAL
    report = json.loads(result.stdout)  # logs went to stderr, not stdout
    assert report["riskLevel"] == "CRITICAL"
    assert report["meta"]["inventoryFile"] == "healthy.json"


def test_score_of_exactly_80_is_not_critical(fakes: dict[str, object]) -> None:
    fakes["risk"] = 80
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-f", "json"])
    assert result.exit_code == 0


@pytest.mark.parametrize(("fmt", "marker"), [("html", "<html"), ("terminal", "Risk score")])
def test_analyze_writes_output_file(tmp_path: Path, fmt: str, marker: str) -> None:
    out = tmp_path / f"report.{fmt}"
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-f", fmt, "-o", str(out)])
    assert result.exit_code == 0
    assert marker in out.read_text(encoding="utf-8")
    assert "\x1b[" not in out.read_text(encoding="utf-8")  # no ANSI codes in files


def test_unwritable_output_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "-f", "json", "-o", str(tmp_path)])
    assert result.exit_code == 1


def test_chaos_flag_reaches_checker(fakes: dict[str, object]) -> None:
    runner.invoke(cli.app, ["analyze", "-r", RUNBOOK, "--chaos", "-f", "json"])
    assert fakes["chaos"] is True
    runner.invoke(cli.app, ["validate", "-i", INVENTORY, "-f", "json"])
    assert fakes["chaos"] is None  # no flag: HEALTH_CHECK_CHAOS setting decides


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (["analyze", "-r", "missing.md"], "NOT_FOUND"),
        (["analyze", "-r", str(REPO / "backend/tests/fixtures/empty.md")], "PARSE_ERROR"),
        (["analyze", "-r", RUNBOOK, "-i", RUNBOOK], "VALIDATION_ERROR"),
        (["validate", "-i", "missing.json"], "NOT_FOUND"),
        (["parse", "-r", str(REPO / "backend/tests/fixtures/empty.md")], "PARSE_ERROR"),
    ],
)
def test_errors_exit_1_with_shared_shape_on_stderr(args: list[str], code: str) -> None:
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 1
    assert json.loads(result.stderr.strip().splitlines()[-1])["code"] == code


def test_invalid_config_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_TOKENS", "lots")
    result = runner.invoke(cli.app, ["parse", "-r", RUNBOOK])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "CONFIG_ERROR"


def test_validate_json_and_terminal() -> None:
    inventory = str(MOCK / "inventories" / "major-outage.json")
    as_json = runner.invoke(cli.app, ["validate", "-i", inventory, "-f", "json"])
    assert as_json.exit_code == 0
    assert len(json.loads(as_json.stdout)) == 7
    as_table = runner.invoke(cli.app, ["validate", "-i", inventory])
    assert "2/7 services UP" in as_table.stdout


def test_parse_prints_runbook_without_raw_markdown() -> None:
    result = runner.invoke(cli.app, ["parse", "-r", RUNBOOK])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["serviceName"] == "Estimate Service"
    assert "rawMarkdown" not in data


def test_main_maps_usage_errors_to_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["analyze", "--bogus"]) == 1
    assert "No such option" in capsys.readouterr().err
    assert cli.main(["analyze"]) == 1  # missing required --runbook
    assert "Missing option" in capsys.readouterr().err
    assert cli.main([]) == 1  # help shown, no empty "Error:" line
    assert "Error:" not in capsys.readouterr().err


def test_main_returns_command_exit_codes(fakes: dict[str, object]) -> None:
    assert cli.main(["version"]) == 0
    fakes["risk"] = 99
    assert cli.main(["analyze", "-r", RUNBOOK, "-f", "json"]) == cli.EXIT_CRITICAL


def test_main_maps_abort_to_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def aborting(**_kwargs: object) -> None:
        raise typer.Abort()

    monkeypatch.setattr(cli, "app", aborting)
    assert cli.main([]) == 1
