"""Execution routes: settings, tools, create/list/get, lifecycle, audit (design section 8).

Every route except `GET /execution/settings` returns `403 EXECUTION_DISABLED`
unless `EXECUTION_ENABLED=true`. Mutating routes return the updated execution;
tool calls then run in the background and clients poll `GET /executions/{id}`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam

from dr_agent.api.analysis_lookup import finished_analysis
from dr_agent.api.deps import AppState, get_state
from dr_agent.api.execution_service import ExecutionService
from dr_agent.api.schemas import ErrorBody
from dr_agent.api.schemas_execution import (
    AuditView,
    CreateExecutionRequest,
    ExecutionSettingsView,
    ExecutionSummary,
    LifecycleRequest,
    ToolView,
)
from dr_agent.execution.analysis_link import analysis_ref, phase_edges
from dr_agent.execution.audit import verify_chain
from dr_agent.execution.models import Execution
from dr_agent.execution.policy import REQUIRED_APPROVALS, effective_risk
from dr_agent.utils.errors import ExecutionDisabledError

router = APIRouter(prefix="/api/v1", tags=["execution"])

State = Annotated[AppState, Depends(get_state)]
ExecutionId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorBody} for code in (403, 404, 409, 422, 429, 502)
}


def get_execution(state: State) -> ExecutionService:
    if state.execution is None:
        raise ExecutionDisabledError("runbook execution is disabled (EXECUTION_ENABLED)")
    return state.execution


Service = Annotated[ExecutionService, Depends(get_execution)]


@router.get("/execution/settings", response_model=ExecutionSettingsView)
async def execution_settings(state: State) -> ExecutionSettingsView:
    """Whether execution is available, so a client can explain why it is not."""
    settings = state.settings
    return ExecutionSettingsView(
        enabled=state.execution is not None,
        allow_live=settings.execution_allow_live,
        approval_timeout_minutes=settings.execution_approval_timeout_minutes,
        max_tool_calls=settings.execution_max_tool_calls,
        approvals_by_risk=dict(REQUIRED_APPROVALS),
    )


@router.get("/tools", response_model=list[ToolView], responses=ERRORS)
async def list_tools(service: Service) -> list[ToolView]:
    """Allow-listed tools with their effective risk class (never server credentials)."""
    policy = service.runtime.policy
    views: list[ToolView] = []
    for spec in service.runtime.tools:
        tool_policy = policy.tool(spec.server, spec.name)
        if tool_policy is not None:
            views.append(
                ToolView(
                    server=spec.server,
                    name=spec.name,
                    description=spec.description,
                    risk=effective_risk(tool_policy.risk, spec),
                    input_schema=spec.input_schema,
                )
            )
    return views


@router.post("/executions", response_model=Execution, status_code=201, responses=ERRORS)
async def create_execution(
    body: CreateExecutionRequest, state: State, service: Service
) -> Execution:
    """Plan an execution from a finished analysis; it follows the report's execution plan.

    `409 CONFLICT` while the analysis is unfinished or failed. Stored analyses
    work after a restart too. `mode: live` needs `EXECUTION_ALLOW_LIVE=true`.
    """
    analysis = await finished_analysis(state, body.analysis_job_id)
    return await service.engine.create(
        analysis.runbook,
        mode=body.mode,
        started_by=body.started_by,
        runbook_label=analysis.runbook_label,
        inferred=phase_edges(analysis.report.execution_plan),
        analysis=analysis_ref(analysis.id, analysis.report),
    )


@router.get("/executions", response_model=list[ExecutionSummary], responses=ERRORS)
async def list_executions(service: Service) -> list[ExecutionSummary]:
    return [ExecutionSummary.of(e) for e in await service.engine.list_all()]


@router.get("/executions/{execution_id}", response_model=Execution, responses=ERRORS)
async def get_execution_detail(execution_id: ExecutionId, service: Service) -> Execution:
    return await service.engine.get(execution_id)


@router.post("/executions/{execution_id}/{action}", response_model=Execution, responses=ERRORS)
async def change_execution(
    execution_id: ExecutionId,
    action: Literal["start", "pause", "resume", "abort", "close"],
    body: LifecycleRequest,
    service: Service,
) -> Execution:
    """Lifecycle. `abort` is the kill switch; calls already sent become `UNKNOWN`."""
    engine, reason = service.engine, body.reason or ""
    if action == "start":
        execution = await engine.start(execution_id, body.actor)
    elif action == "resume":
        execution = await engine.resume(execution_id, body.actor)
    elif action == "pause":
        execution = await engine.pause(execution_id, body.actor, reason)
    elif action == "close":
        execution = await engine.close(execution_id, body.actor, reason)
    else:
        execution = await engine.abort(execution_id, body.actor, reason)
    return service.kick(execution)


@router.get("/executions/{execution_id}/audit", response_model=AuditView, responses=ERRORS)
async def get_audit(
    execution_id: ExecutionId,
    service: Service,
    verify: Annotated[bool, Query(description="Recompute the hash chain")] = False,
) -> AuditView:
    events, _ = await service.engine.audit(execution_id)
    return AuditView(
        events=events, verification=verify_chain(execution_id, events) if verify else None
    )
