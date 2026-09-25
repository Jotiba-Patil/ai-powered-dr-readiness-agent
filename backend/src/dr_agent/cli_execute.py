"""`dr-agent execute`: analyze a runbook, then (if the operator agrees) run it step by step.

Execution always follows an analysis: the readiness report is produced first
(same pipeline as `analyze`, stored in the history) or loaded with
`--analysis ID`; its risk and plan are shown, and the operator is asked
whether to execute. The execution then follows the report's execution
plan. Uses the same engine, policy, store and MCP servers as the API (see
`execution_runtime.py`), so `EXECUTION_ENABLED` (and `EXECUTION_ALLOW_LIVE` for
`--live`) must be set. Exit codes: 0 completed or not executed, 2 failed or
aborted, 1 error.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console

from dr_agent.cli_analysis import run_analysis, stored_analysis
from dr_agent.cli_execute_steps import Ask, Outcome, handle_step, pending_steps
from dr_agent.cli_execute_view import show_analysis, show_history_state
from dr_agent.config import Settings
from dr_agent.execution.analysis_link import analysis_ref, phase_edges
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import AnalysisRef, Execution, ExecutionMode, ExecutionState
from dr_agent.execution.transitions import TERMINAL_EXECUTION_STATES
from dr_agent.execution_runtime import open_execution_runtime
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import ExecutionDisabledError, ValidationError
from dr_agent.wiring import build_checker, build_llm

EXIT_COMPLETED, EXIT_FAILED = 0, 2


async def run_session(
    engine: ExecutionEngine,
    runbook: Runbook,
    *,
    operator: str,
    mode: ExecutionMode,
    label: str,
    ask: Ask,
    console: Console,
    inferred: Iterable[tuple[int, Iterable[int]]] = (),
    analysis: AnalysisRef | None = None,
    history: ServiceHistory | None = None,
) -> Execution:
    execution = await engine.create(
        runbook,
        mode=mode,
        started_by=operator,
        runbook_label=label,
        inferred=inferred,
        analysis=analysis,
    )
    console.print(f"Execution [bold]{execution.id}[/] ({mode.value}) for {label}")
    await engine.start(execution.id, operator)
    past = {step.step_number: step for step in (history.steps if history else [])}
    while True:
        execution = await engine.advance(execution.id)
        if execution.state in TERMINAL_EXECUTION_STATES:
            return execution
        pending = pending_steps(execution)
        if pending:
            outcome = await handle_step(
                engine,
                execution,
                pending[0],
                operator=operator,
                ask=ask,
                console=console,
                past=past.get(pending[0].step_number),
            )
            if outcome is Outcome.ABORT:
                return await engine.abort(execution.id, operator, ask("Reason for aborting"))
            if outcome is Outcome.CLOSE:
                return await engine.close(execution.id, operator, ask("Reason for closing"))
        elif execution.state is not ExecutionState.PAUSED:
            return execution  # pragma: no cover - the engine always leaves work for a person
        await _resume_if_paused(engine, execution.id, operator, console)


async def _resume_if_paused(
    engine: ExecutionEngine, execution_id: str, operator: str, console: Console
) -> None:
    """In the terminal the operator has just decided what to do, so carry on."""
    execution = await engine.get(execution_id)
    if execution.state is ExecutionState.PAUSED:
        console.print(f"[yellow]Paused: {execution.pause_reason}. Resuming.[/]")
        await engine.resume(execution_id, operator)


async def execute_runbook(
    settings: Settings,
    runbook_path: Path | None,
    *,
    analysis_id: str | None = None,
    inventory_path: Path | None,
    operator: str,
    live: bool,
    ask: Ask,
    confirm: Callable[[str], bool],
    console: Console,
) -> Execution | None:
    """Analyzes (or loads `analysis_id`), asks, then executes; None when the operator declines."""
    # Fail before a (possibly minutes-long) analysis if execution could not follow it.
    if not settings.execution_enabled:
        raise ExecutionDisabledError("runbook execution is disabled (EXECUTION_ENABLED)")
    if live and not settings.execution_allow_live:
        raise ExecutionDisabledError("live execution is not allowed (EXECUTION_ALLOW_LIVE)")
    rng = random.Random()  # noqa: S311 -- retry jitter and mock latency only, not security
    async with httpx.AsyncClient() as client:
        llm = build_llm(settings, client, rng)
        if analysis_id is not None:
            analysis = await stored_analysis(settings, analysis_id)
        else:
            if runbook_path is None:
                raise ValidationError("give a runbook or a stored analysis")
            with console.status("Analyzing runbook (an LLM on CPU can take minutes)"):
                analysis = await run_analysis(
                    settings,
                    runbook_path,
                    inventory_path,
                    llm=llm,
                    checker=build_checker(settings, client, rng),
                    save=True,
                )
        record = analysis.record
        show_analysis(console, record.report)
        show_history_state(console, analysis)
        mode = ExecutionMode.LIVE if live else ExecutionMode.DRY_RUN
        if not confirm(f"Execute this runbook now ({mode.value})?"):
            console.print("Not executed.")
            return None
        async with open_execution_runtime(settings, llm, rng=rng) as runtime:
            for execution_id in runtime.recovered:
                console.print(f"[yellow]Recovered interrupted execution {execution_id}[/]")
            final = await run_session(
                runtime.engine,
                record.runbook,
                operator=operator,
                mode=mode,
                label=record.runbook_label,
                ask=ask,
                console=console,
                inferred=phase_edges(record.report.execution_plan),
                analysis=analysis_ref(record.id, record.report),
                history=record.report.historical_insights,
            )
            _, chain = await runtime.engine.audit(final.id)
            console.print(
                f"Execution {final.id}: [bold]{final.state.value}[/]; audit chain "
                f"{'valid' if chain.valid else 'BROKEN'} (head {chain.head[:16]}...)"
            )
            return final


OperatorOpt = Annotated[
    str, typer.Option("--operator", help="Your name; recorded as the one who started the run.")
]
LiveOpt = Annotated[
    bool, typer.Option("--live", help="Call the MCP tools (default: dry run, nothing is called).")
]


def exit_code(execution: Execution | None) -> int:
    """0 when completed or not executed at all; 2 when it failed or was aborted."""
    if execution is None or execution.state is ExecutionState.COMPLETED:
        return EXIT_COMPLETED
    return EXIT_FAILED
