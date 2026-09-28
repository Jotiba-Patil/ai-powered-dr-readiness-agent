"""Schedule routes: create, read, update, delete, pause, resume, run now, runs (ADR 0010).

Every route returns `403 SCHEDULER_DISABLED` unless `SCHEDULER_ENABLED=true`. The
scheduler only analyzes; a scheduled run is executed with the existing
`POST /api/v1/executions {analysisJobId: run.analysisId}`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam

from dr_agent.api.deps import AppState, get_state
from dr_agent.api.schemas import ErrorBody
from dr_agent.api.schemas_schedules import (
    CreateScheduleRequest,
    PauseRequest,
    ResumeRequest,
    RunPage,
    ScheduleView,
)
from dr_agent.scheduling.models import ScheduleRun, ScheduleSpec
from dr_agent.scheduling.service import ScheduleService
from dr_agent.utils.errors import SchedulerDisabledError

router = APIRouter(prefix="/api/v1", tags=["schedules"])

State = Annotated[AppState, Depends(get_state)]
ScheduleId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorBody} for code in (403, 404, 409, 422, 429)
}
MAX_RUNS_PAGE = 100


def get_schedules(state: State) -> ScheduleService:
    if state.schedules is None:
        raise SchedulerDisabledError("scheduled analysis is disabled (SCHEDULER_ENABLED)")
    return state.schedules


Service = Annotated[ScheduleService, Depends(get_schedules)]


async def _view(service: ScheduleService, schedule_id: str) -> ScheduleView:
    schedule = await service.store.get(schedule_id)
    runs = await service.store.list_runs(schedule_id, limit=1)
    return ScheduleView.of(schedule, runs[0] if runs else None)


@router.get("/schedules", response_model=list[ScheduleView], responses=ERRORS)
async def list_schedules(service: Service) -> list[ScheduleView]:
    """All schedules, oldest first, each with its latest run."""
    latest = await service.store.latest_runs()
    return [ScheduleView.of(s, latest.get(s.id)) for s in await service.store.list_all()]


@router.post("/schedules", response_model=ScheduleView, status_code=201, responses=ERRORS)
async def create_schedule(
    body: CreateScheduleRequest, state: State, service: Service
) -> ScheduleView:
    """Paths are relative to `API_ALLOWED_DIR` and checked now and on every run."""
    spec = ScheduleSpec.model_validate(body.model_dump(exclude={"created_by"}))
    if "timezone" not in body.model_fields_set:
        spec = spec.model_copy(update={"timezone": state.settings.scheduler_default_timezone})
    schedule = await service.create(spec, created_by=body.created_by)
    return ScheduleView.of(schedule, None)


@router.get("/schedules/{schedule_id}", response_model=ScheduleView, responses=ERRORS)
async def get_schedule(schedule_id: ScheduleId, service: Service) -> ScheduleView:
    return await _view(service, schedule_id)


@router.put("/schedules/{schedule_id}", response_model=ScheduleView, responses=ERRORS)
async def update_schedule(
    schedule_id: ScheduleId, body: ScheduleSpec, service: Service
) -> ScheduleView:
    """Replaces the settings; a paused schedule stays paused."""
    await service.update(schedule_id, body)
    return await _view(service, schedule_id)


@router.delete("/schedules/{schedule_id}", status_code=204, responses=ERRORS)
async def delete_schedule(schedule_id: ScheduleId, service: Service) -> Response:
    """Cancels a running run first; the analyses stay in the history."""
    await service.delete(schedule_id)
    return Response(status_code=204)


@router.post("/schedules/{schedule_id}/pause", response_model=ScheduleView, responses=ERRORS)
async def pause_schedule(
    schedule_id: ScheduleId, body: PauseRequest, service: Service
) -> ScheduleView:
    """`until` resumes it automatically (at most `SCHEDULER_MAX_PAUSE_DAYS` ahead)."""
    await service.pause(schedule_id, by=body.by, until=body.until)
    return await _view(service, schedule_id)


@router.post("/schedules/{schedule_id}/resume", response_model=ScheduleView, responses=ERRORS)
async def resume_schedule(
    schedule_id: ScheduleId, body: ResumeRequest, service: Service
) -> ScheduleView:
    """Continues from the next slot after now; missed slots are skipped."""
    await service.resume(schedule_id, by=body.by)
    return await _view(service, schedule_id)


@router.post(
    "/schedules/{schedule_id}/run-now",
    response_model=ScheduleRun,
    status_code=202,
    responses=ERRORS,
)
async def run_now(schedule_id: ScheduleId, service: Service) -> ScheduleRun:
    """Starts a run now (also while paused); `409` while a run of it is still going."""
    return await service.run_now(schedule_id)


@router.get("/schedules/{schedule_id}/runs", response_model=RunPage, responses=ERRORS)
async def list_runs(
    schedule_id: ScheduleId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=MAX_RUNS_PAGE)] = 20,
    before: Annotated[datetime | None, Query(description="`nextBefore` of the last page")] = None,
) -> RunPage:
    """Runs of a schedule, newest first."""
    await service.store.get(schedule_id)  # 404 for an unknown schedule
    items = await service.store.list_runs(schedule_id, limit=limit, before=before)
    next_before = items[-1].started_at if len(items) == limit else None
    return RunPage(items=items, next_before=next_before)
