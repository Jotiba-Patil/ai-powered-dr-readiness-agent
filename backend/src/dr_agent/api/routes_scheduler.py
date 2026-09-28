"""Scheduler-wide routes: state, pause all, resume all, recipient preview, single runs.

Like the schedule routes, all return `403 SCHEDULER_DISABLED` while it is off.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi import Path as PathParam

from dr_agent.api.routes_schedules import ERRORS, Service, State
from dr_agent.api.schemas_schedules import (
    PauseRequest,
    RecipientPreview,
    ResumeRequest,
    SchedulerView,
)
from dr_agent.scheduling.models import MAX_RECIPIENTS, ScheduleRun, ScheduleSpec

router = APIRouter(prefix="/api/v1", tags=["schedules"])

RunId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


@router.get("/scheduler", response_model=SchedulerView, responses=ERRORS)
async def scheduler_state(state: State, service: Service) -> SchedulerView:
    """Whether everything is paused, and the limits the dashboard needs."""
    return SchedulerView.of(await service.store.get_state(), state.settings)


@router.post("/scheduler/pause", response_model=SchedulerView, responses=ERRORS)
async def pause_all(body: PauseRequest, state: State, service: Service) -> SchedulerView:
    """No schedule starts a run until resumed (or until `until`); running runs finish."""
    paused = await service.pause_all(by=body.by, until=body.until)
    return SchedulerView.of(paused, state.settings)


@router.post("/scheduler/resume", response_model=SchedulerView, responses=ERRORS)
async def resume_all(body: ResumeRequest, state: State, service: Service) -> SchedulerView:
    """Every active schedule continues from its next slot after now."""
    return SchedulerView.of(await service.resume_all(by=body.by), state.settings)


@router.get("/scheduler/recipient-preview", response_model=RecipientPreview, responses=ERRORS)
async def recipient_preview(
    service: Service,
    runbook_path: Annotated[str, Query(alias="runbookPath", min_length=1, max_length=512)],
    recipients: Annotated[list[str] | None, Query(max_length=MAX_RECIPIENTS)] = None,
) -> RecipientPreview:
    """Who a run of this runbook would email now (reads the runbook's owner)."""
    spec = ScheduleSpec.model_validate(
        {
            "name": "preview",
            "runbook_path": runbook_path,
            "cadence": {"kind": "hourly", "minute": 0},
        }
        | ({"recipients": recipients} if recipients else {})
    )
    resolved = await service.preview_recipients(spec.runbook_path, spec.recipients)
    return RecipientPreview.of(resolved)


@router.get("/schedule-runs/{run_id}", response_model=ScheduleRun, responses=ERRORS)
async def get_run(run_id: RunId, service: Service) -> ScheduleRun:
    """One run; execute it with `POST /executions {analysisJobId: analysisId}`."""
    return await service.store.get_run(run_id)


@router.post("/schedule-runs/{run_id}/cancel", response_model=ScheduleRun, responses=ERRORS)
async def cancel_run(run_id: RunId, service: Service) -> ScheduleRun:
    """Stops a running run and its analysis; no email is sent. `409` if it is not running."""
    return await service.cancel_run(run_id)
