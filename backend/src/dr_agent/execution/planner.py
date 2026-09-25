"""Runbook -> `Execution`: one `StepRun` per step, in execution-phase order.

Phases come from the same code as the readiness report (`compute_execution_plan`
over `merge_depends_on`), so the executed order matches the analyzed plan.
Each step is then classified (design section 4.2):

- annotated call that passes policy -> `AWAITING_APPROVAL` (source `annotated`)
- annotated call that fails policy  -> `PROPOSED`, with the problems listed
- no annotation, valid AI proposal  -> `PROPOSED` (source `ai_proposed`), needs review
- no annotation, no usable proposal -> `AWAITING_MANUAL`, with the reason

The runbook text itself is not kept, only its SHA-256.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from dr_agent.core.dependency_graph import merge_depends_on
from dr_agent.core.execution_plan import compute_execution_plan
from dr_agent.execution.audit import AuditEvent, genesis_hash
from dr_agent.execution.canonical import sha256_hex
from dr_agent.execution.journal import SYSTEM_ACTOR, AuditType, Journal
from dr_agent.execution.models import (
    AnalysisRef,
    CallKind,
    CallSource,
    Execution,
    ExecutionMode,
    ProposalNote,
    StepRun,
    ToolCall,
)
from dr_agent.execution.policy import Catalog
from dr_agent.execution.policy_file import ExecutionPolicy
from dr_agent.execution.proposer import ProposalOutcome
from dr_agent.execution.step_calls import evaluate_step_calls
from dr_agent.execution.transitions import StepEvent
from dr_agent.models.runbook import PlannedToolCall, Runbook, Step


def plan_execution(
    runbook: Runbook,
    *,
    policy: ExecutionPolicy,
    catalog: Catalog,
    execution_id: str,
    mode: ExecutionMode,
    started_by: str,
    runbook_label: str,
    now: datetime,
    inferred: Iterable[tuple[int, Iterable[int]]] = (),
    proposals: Mapping[int, ProposalOutcome] | None = None,
    analysis: AnalysisRef | None = None,
) -> tuple[Execution, list[AuditEvent]]:
    depends_on = merge_depends_on(runbook.steps, inferred)
    phases = compute_execution_plan(runbook.steps, depends_on)
    phase_of = {number: phase.phase for phase in phases for number in phase.steps}
    steps = sorted(runbook.steps, key=lambda s: (phase_of[s.step_number], s.step_number))

    execution = Execution(
        id=execution_id,
        mode=mode,
        runbook_label=runbook_label,
        runbook_sha256=sha256_hex(runbook.raw_markdown),
        started_by=started_by,
        created_at=now,
        updated_at=now,
        steps=[_step_run(step, phase_of[step.step_number], depends_on) for step in steps],
        audit_head=genesis_hash(execution_id),
        analysis=analysis,
    )
    journal = Journal(execution, now)
    journal.record(
        AuditType.EXECUTION_CREATED,
        started_by,
        {
            "mode": mode.value,
            "runbookLabel": runbook_label,
            "runbookSha256": execution.runbook_sha256,
            "steps": len(steps),
            "phases": len(phases),
            "analysis": analysis.model_dump(mode="json", by_alias=True) if analysis else None,
        },
    )
    for step, run in zip(steps, execution.steps, strict=True):
        proposal = (proposals or {}).get(step.step_number)
        _classify(journal, run, step, policy, catalog, proposal)
    return execution, journal.events


def _step_run(step: Step, phase: int, depends_on: dict[int, set[int]]) -> StepRun:
    return StepRun(
        step_number=step.step_number,
        phase=phase,
        action=step.action,
        owner=step.owner,
        target_system=step.target_system,
        estimated_minutes=step.estimated_minutes,
        depends_on=sorted(depends_on[step.step_number]),
    )


def _classify(
    journal: Journal,
    run: StepRun,
    step: Step,
    policy: ExecutionPolicy,
    catalog: Catalog,
    proposal: ProposalOutcome | None,
) -> None:
    if step.tool_call is None:
        _unannotated(journal, run, policy, catalog, proposal)
        return
    run.call = _annotated(step.tool_call, CallKind.MAIN)
    run.verify = _annotated(step.verify_call, CallKind.VERIFY)
    run.rollback = _annotated(step.rollback_call, CallKind.ROLLBACK)
    run.policy_errors = evaluate_step_calls(run, policy, catalog)
    if run.policy_errors:
        journal.move_step(run, StepEvent.NEEDS_REVIEW, SYSTEM_ACTOR, "; ".join(run.policy_errors))
    else:
        journal.move_step(run, StepEvent.CALL_READY, SYSTEM_ACTOR)


def _unannotated(
    journal: Journal,
    run: StepRun,
    policy: ExecutionPolicy,
    catalog: Catalog,
    proposal: ProposalOutcome | None,
) -> None:
    if proposal is None or proposal.call is None:
        reason = proposal.reason if proposal and proposal.reason else "no tool annotation"
        journal.move_step(run, StepEvent.NO_CALL, SYSTEM_ACTOR, f"{reason}: manual step")
        return
    run.call = ToolCall.from_planned(proposal.call, CallKind.MAIN, CallSource.AI_PROPOSED)
    run.proposal = ProposalNote(rationale=proposal.rationale, confidence=proposal.confidence)
    run.policy_errors = evaluate_step_calls(run, policy, catalog)
    journal.record(
        AuditType.PROPOSAL,
        SYSTEM_ACTOR,
        {
            "step": run.step_number,
            "server": run.call.server,
            "tool": run.call.tool,
            "callHash": run.call.call_hash,
            "confidence": proposal.confidence,
        },
    )
    journal.move_step(
        run, StepEvent.NEEDS_REVIEW, SYSTEM_ACTOR, "AI-proposed call: review before approval"
    )


def _annotated(planned: PlannedToolCall | None, kind: CallKind) -> ToolCall | None:
    if planned is None:
        return None
    return ToolCall.from_planned(planned, kind, CallSource.ANNOTATED)
