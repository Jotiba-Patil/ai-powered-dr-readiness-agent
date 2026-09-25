"""Terminal prompts for one step that needs a person (`dr-agent execute`).

Every answer becomes a typed decision for the engine, which does all checks;
a refused answer (wrong hash, same approver twice, missing reason, ...) is
printed and asked again. The call is always shown before anyone approves it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum

from rich.console import Console
from rich.panel import Panel

from dr_agent.execution.decisions import (
    Approve,
    ConvertToManual,
    Decision,
    EditCall,
    MarkDone,
    Reject,
    ReportOutcome,
    Retry,
    Skip,
)
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import CallKind, Execution, StepRun, StepState, ToolCall
from dr_agent.execution.policy import REQUIRED_APPROVALS
from dr_agent.models.insights import StepHistory
from dr_agent.utils.errors import AppError

Ask = Callable[[str], str]
NEEDS_PERSON = frozenset(
    {
        StepState.PROPOSED,
        StepState.AWAITING_APPROVAL,
        StepState.REJECTED,
        StepState.AWAITING_MANUAL,
        StepState.FAILED,
        StepState.UNKNOWN,
    }
)


class Outcome(StrEnum):
    CONTINUE = "continue"
    ABORT = "abort"
    CLOSE = "close"


def pending_steps(execution: Execution) -> list[StepRun]:
    """Steps a person must act on, including approved steps blocked by a rolled-back one."""
    rolled_back = {r.step_number for r in execution.steps if r.state is StepState.ROLLED_BACK}
    pending: list[StepRun] = []
    for run in execution.steps:
        waiting_to_verify = run.state is StepState.VERIFYING and run.verify is None
        blocked = run.state is StepState.APPROVED and bool(rolled_back & set(run.depends_on))
        if run.state in NEEDS_PERSON or waiting_to_verify or blocked:
            pending.append(run)
    return pending


def show_step(console: Console, run: StepRun, past: StepHistory | None = None) -> None:
    lines = [f"[bold]{run.action}[/] (owner {run.owner}, {run.estimated_minutes:g} min)"]
    if past is not None:
        lines.append(previous_runs(past))
    lines.append(f"State: {run.state.value}" + (f" - {run.summary}" if run.summary else ""))
    for call in (run.call, run.verify, run.rollback):
        if call is not None:
            lines.append(_describe(call))
    if run.proposal is not None:
        lines.append(f"AI rationale (unverified): {run.proposal.rationale}")
    lines.extend(f"[red]Policy: {problem}[/]" for problem in run.policy_errors)
    console.print(Panel("\n".join(lines), title=f"Step {run.step_number}", expand=False))


def previous_runs(past: StepHistory) -> str:
    """Information only (ADR 0009): it never approves, skips or changes anything."""
    median = past.median_active_minutes
    timing = f", median {median:g} min" if median is not None else ""
    return (
        f"[dim]Previous live runs: {past.live_runs}, failed {past.failed}, "
        f"rolled back {past.rolled_back}{timing}[/]"
    )


def _describe(call: ToolCall) -> str:
    risk = call.risk_class.value if call.risk_class else "not allowed"
    needed = REQUIRED_APPROVALS.get(call.risk_class, 0) if call.risk_class else 0
    arguments = json.dumps(call.arguments, sort_keys=True)
    return (
        f"{call.kind.value}: [cyan]{call.server}/{call.tool}[/] {arguments}  "
        f"risk={risk} source={call.source.value} approvals={len(call.approvals)}/{needed}"
    )


async def handle_step(
    engine: ExecutionEngine,
    execution: Execution,
    run: StepRun,
    *,
    operator: str,
    ask: Ask,
    console: Console,
    past: StepHistory | None = None,
) -> Outcome:
    """Asks until the step moves on (or the operator aborts or closes the execution)."""
    show_step(console, run, past)
    while True:
        answer = ask(_question(run)).strip()
        choice = answer.lower()
        if choice == "abort":
            return Outcome.ABORT
        if choice == "close" and run.state in (StepState.FAILED, StepState.APPROVED):
            return Outcome.CLOSE
        try:
            if choice == "rollback" and run.state is StepState.FAILED:
                await _rollback(engine, execution, run, operator, ask)
            else:
                decision = _decision(run, choice, answer, operator, ask)
                if decision is None:
                    console.print(f"[yellow]Not an option here: {answer!r}[/]")
                    continue
                await engine.decide(execution.id, run.step_number, decision)
        except AppError as exc:
            console.print(f"[red]{exc.code}: {exc.message}[/]")
            run = (await engine.get(execution.id)).step(run.step_number)
            continue
        return Outcome.CONTINUE


def _question(run: StepRun) -> str:
    return {
        StepState.AWAITING_APPROVAL: "Approver name, or reject / skip / abort",
        StepState.PROPOSED: "accept / manual / skip / abort",
        StepState.REJECTED: "manual / skip / abort",
        StepState.AWAITING_MANUAL: "done / skip / abort",
        StepState.FAILED: "retry / rollback / skip / close / abort",
        StepState.APPROVED: "Blocked by a rolled-back step: skip / close / abort",
    }.get(run.state, "Did it work? ok / failed / abort")


def _decision(run: StepRun, choice: str, answer: str, actor: str, ask: Ask) -> Decision | None:
    if choice == "skip":
        return Skip(actor, ask("Reason for skipping"))
    if run.state is StepState.AWAITING_APPROVAL and run.call is not None:
        if choice == "reject":
            return Reject(actor, ask("Reason for rejecting"))
        return Approve(answer, run.call.call_hash)
    if run.state is StepState.PROPOSED and choice == "accept":
        return EditCall(actor)
    if run.state in (StepState.PROPOSED, StepState.REJECTED) and choice == "manual":
        return ConvertToManual(actor, ask("Why by hand"))
    if run.state is StepState.AWAITING_MANUAL and choice == "done":
        return MarkDone(actor, ask("What was done"))
    if run.state is StepState.FAILED and choice == "retry":
        return Retry(actor)
    if choice in ("ok", "failed") and run.state in (StepState.VERIFYING, StepState.UNKNOWN):
        return ReportOutcome(actor, choice == "ok", ask("What did you check"))
    return None


async def _rollback(
    engine: ExecutionEngine, execution: Execution, run: StepRun, operator: str, ask: Ask
) -> None:
    rollback = run.rollback
    if rollback is None:
        raise AppError("this step has no rollback call")
    needed = REQUIRED_APPROVALS.get(rollback.risk_class, 1) if rollback.risk_class else 1
    for number in range(1, needed + 1):
        name = ask(f"Rollback approver {number} of {needed}")
        decision = Approve(name, rollback.call_hash, kind=CallKind.ROLLBACK)
        await engine.decide(execution.id, run.step_number, decision)
    await engine.rollback(execution.id, run.step_number, operator)
