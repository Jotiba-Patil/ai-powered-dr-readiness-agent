"""One real-process test of the CLI's exit codes and stdout/stderr split.

Runs with `LLM_PROVIDER=none` (rule-based analysis, no model call, no network).
"""

import json
import os
import subprocess
import sys

import pytest
from conftest import MOCK, REPO

RUN_CLI = [sys.executable, "-c", "from dr_agent.cli import run; run()"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LLM_PROVIDER": "none", "HEALTH_CHECKER": "mock", "LOG_LEVEL": "info"}
    return subprocess.run(  # noqa: S603 -- fixed interpreter + args, no shell
        [*RUN_CLI, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=REPO,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        (["version"], 0),
        (["analyze", "--runbook", "mock-data/runbooks/nope.md"], 1),
        (["analyze", "--no-such-flag"], 1),
    ],
)
def test_exit_codes(args: list[str], exit_code: int) -> None:
    assert _run(*args).returncode == exit_code


def test_analyze_json_rule_based_exit_0_with_clean_stdout() -> None:
    result = _run(
        "analyze",
        "--runbook",
        str(MOCK / "runbooks" / "estimate-service.md"),
        "--inventory",
        str(MOCK / "inventories" / "healthy.json"),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["aiAnalysisAvailable"] is False
    assert report["riskScore"] <= 80
