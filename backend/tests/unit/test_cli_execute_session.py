"""`dr-agent execute` session loop with scripted answers and an in-memory engine."""

import io
from pathlib import Path

from exec_support import OPERATOR, drsim_catalog, executable_runbook, make_engine
from rich.console import Console

from dr_agent.cli_execute import exit_code, run_session
from dr_agent.execution.models import Execution, ExecutionMode, ExecutionState, StepState
from dr_agent.tools.base import ToolResult
from dr_agent.tools.fake import FakeExecutor


class Script:
    """Answers questions in order and remembers what was asked."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        if not self.answers:
            raise AssertionError(f"no scripted answer for: {question}")
        return self.answers.pop(0)


async def _run(
    tmp_path: Path, script: Script, executor: FakeExecutor | None = None
) -> tuple[Execution, str]:
    engine, _, _ = await make_engine(tmp_path, executor or FakeExecutor(drsim_catalog()))
    out = io.StringIO()
    execution = await run_session(
        engine,
        executable_runbook(),
        operator=OPERATOR,
        mode=ExecutionMode.LIVE,
        label="sample.md",
        ask=script,
        console=Console(file=out, width=200),
    )
    return execution, out.getvalue()


HAPPY = ("Ann", "ok", "dashboard shows the outage", "Ann", "Ann", "Ben", "Ann", "Ann", "Ben")


async def test_happy_path_completes(tmp_path: Path) -> None:
    script = Script(*HAPPY)
    execution, output = await _run(tmp_path, script)
    assert execution.state is ExecutionState.COMPLETED
    assert exit_code(execution) == 0
    assert "drsim/db_promote_replica" in output
    assert "risk=destructive" in output
    assert script.questions[1] == "Did it work? ok / failed / abort"


async def test_refused_answers_are_asked_again(tmp_path: Path) -> None:
    # "Olivia" started the run and cannot approve the destructive step 3; "maybe" is no option.
    script = Script("Ann", "maybe", "ok", "checked", "Ann", "Olivia", "Ann", "Ben", *HAPPY[6:])
    execution, output = await _run(tmp_path, script)
    assert execution.state is ExecutionState.COMPLETED
    assert "Not an option here: 'maybe'" in output
    assert "POLICY_VIOLATION" in output


async def test_failure_rollback_then_blocked_step_is_closed(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog())
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="crashloop"))
    script = Script(
        "Ann",
        "ok",
        "checked",
        "Ann",  # steps 1 and 2 (2 fails)
        "rollback",
        "Ann",  # undo needs one approval (write)
        "Ann",
        "Ben",
        "Ann",
        "Ann",
        "Ben",  # steps 3-5 approved
        "close",
        "standby restart failed",  # step 5 is blocked by the rolled-back step 2
    )
    execution, output = await _run(tmp_path, script, executor)
    assert execution.state is ExecutionState.FAILED
    assert exit_code(execution) == 2
    assert execution.step(2).state is StepState.ROLLED_BACK
    assert "Blocked by a rolled-back step" in script.questions[-2]
    assert "Paused: step 2 failed. Resuming." in output


async def test_abort(tmp_path: Path) -> None:
    execution, _ = await _run(tmp_path, Script("abort", "not today"))
    assert execution.state is ExecutionState.ABORTED
    assert exit_code(execution) == 2


async def test_reject_then_manual_and_retry(tmp_path: Path) -> None:
    executor = FakeExecutor(drsim_catalog())
    executor.script("drsim", "k8s_rollout_restart", ToolResult(ok=False, content="flaky"))
    script = Script(
        "reject",
        "wrong region",  # step 1
        "manual",
        "checked by phone",  # step 1 becomes manual
        "done",
        "outage confirmed",  # manual step 1 done
        "Ann",  # step 2 approved, fails
        "retry",
        "Ann",  # retry needs a fresh approval
        "Ann",
        "Ben",
        "Ann",
        "Ann",
        "Ben",
    )
    execution, _ = await _run(tmp_path, script, executor)
    assert execution.state is ExecutionState.COMPLETED
    assert execution.step(1).state is StepState.MANUAL_DONE
    assert execution.step(2).attempt == 2


async def test_skip_asks_for_a_reason(tmp_path: Path) -> None:
    script = Script("skip", "not needed", "abort", "enough")
    execution, _ = await _run(tmp_path, script)
    assert execution.step(1).state is StepState.SKIPPED
    assert script.questions[1] == "Reason for skipping"
