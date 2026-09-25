"""Human decisions on one step: edit or accept a call, approve, reject, skip, and so on.

All checks (states, policy, call hash, two-person rule) happen in `execution/`;
these routes only translate request bodies into `Decision`s. `rollback` runs the
approved rollback call within the request (bounded by the tool timeout).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from fastapi import Path as PathParam

from dr_agent.api.routes_execution import ERRORS, ExecutionId, Service
from dr_agent.api.schemas_execution import ApproveRequest, CallRequest, StepDecisionRequest
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
from dr_agent.execution.models import Execution
from dr_agent.utils.errors import ValidationError

router = APIRouter(
    prefix="/api/v1/executions/{execution_id}/steps/{step_number}", tags=["execution"]
)
StepNumber = Annotated[int, PathParam(ge=1, le=10_000)]


@router.put("/call", response_model=Execution, responses=ERRORS)
async def set_call(
    execution_id: ExecutionId, step_number: StepNumber, body: CallRequest, service: Service
) -> Execution:
    """Accept (omit `call`) or replace a call. Clears the step's approvals."""
    decision = EditCall(editor=body.editor, call=body.call, kind=body.kind)
    return await service.engine.decide(execution_id, step_number, decision)


@router.post("/approve", response_model=Execution, responses=ERRORS)
async def approve(
    execution_id: ExecutionId, step_number: StepNumber, body: ApproveRequest, service: Service
) -> Execution:
    """Approve the call with the hash you were shown (`409 STALE_CALL` if it changed)."""
    decision = Approve(body.approver, body.call_hash, body.comment, body.kind)
    execution = await service.engine.decide(execution_id, step_number, decision)
    return service.kick(execution)


@router.post("/{action}", response_model=Execution, responses=ERRORS)
async def decide(
    execution_id: ExecutionId,
    step_number: StepNumber,
    action: Literal["reject", "skip", "manual", "mark-done", "verify", "retry", "rollback"],
    body: StepDecisionRequest,
    service: Service,
) -> Execution:
    if action == "rollback":
        execution = await service.engine.rollback(execution_id, step_number, body.actor)
        return service.kick(execution)
    execution = await service.engine.decide(execution_id, step_number, _decision(action, body))
    return service.kick(execution)


def _decision(action: str, body: StepDecisionRequest) -> Decision:
    reason = body.reason or ""
    match action:
        case "reject":
            return Reject(body.actor, reason)
        case "skip":
            return Skip(body.actor, reason)
        case "manual":
            return ConvertToManual(body.actor, reason)
        case "mark-done":
            return MarkDone(body.actor, body.reason or "done by hand")
        case "retry":
            return Retry(body.actor)
        case _:
            if body.succeeded is None:
                raise ValidationError("verify needs 'succeeded'", details={"field": "succeeded"})
            outcome = "confirmed" if body.succeeded else "reported failed"
            return ReportOutcome(body.actor, body.succeeded, body.reason or f"{outcome} by hand")
