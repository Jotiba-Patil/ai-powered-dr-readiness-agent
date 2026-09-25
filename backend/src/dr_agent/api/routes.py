"""HTTP routes. No business logic here: input -> service calls -> response.

Analysis is job-based (plan decision D3): `POST`/`GET /dr/analyze` return 202
with a job id and a `Location` header to poll. `?wait=true` waits up to
`API_WAIT_TIMEOUT_SECONDS` and returns the report itself (200, the brief's
response shape) if the job finished in time, else still 202.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, JSONResponse

from dr_agent import __version__
from dr_agent.api.analysis_lookup import finished_analysis, job_view
from dr_agent.api.body import read_analyze_input
from dr_agent.api.deps import AppState, get_state
from dr_agent.api.middleware import REPORT_CSP
from dr_agent.api.openapi import ANALYZE_REQUEST_BODY
from dr_agent.api.paths import resolve_allowed_path
from dr_agent.api.schemas import ErrorBody, HealthResponse, JobState, JobView
from dr_agent.formatters.format_html import format_html
from dr_agent.loaders import load_inventory, read_text_file
from dr_agent.models.inventory import SystemInventory
from dr_agent.models.report import DRReadinessReport
from dr_agent.models.runbook import Runbook
from dr_agent.service import analyze_runbook, parse_markdown

router = APIRouter(prefix="/api/v1")

State = Annotated[AppState, Depends(get_state)]
JobId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Wait = Annotated[bool, Query(description="Wait (bounded) and return the report if done.")]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorBody} for code in (400, 403, 404, 413, 422, 429, 500)
}
_ANALYZE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"model": DRReadinessReport, "description": "wait=true and the job finished in time"},
    202: {"model": JobView, "description": "Job accepted; poll the Location header"},
    **_ERRORS,
}


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health(state: State) -> HealthResponse:
    return HealthResponse(version=__version__, uptime=round(state.uptime_seconds, 3))


@router.post(
    "/dr/analyze",
    tags=["analysis"],
    status_code=202,
    responses=_ANALYZE_RESPONSES,
    openapi_extra=ANALYZE_REQUEST_BODY,
)
async def post_analyze(request: Request, state: State, wait: Wait = False) -> JSONResponse:
    """Analyze an uploaded runbook: multipart (`runbook` + optional `inventory` files) or JSON."""
    data = await read_analyze_input(request, state.settings.api_max_upload_bytes)
    runbook = parse_markdown(data.runbook_markdown)
    return await _submit(
        state, runbook, data.inventory, data.runbook_label, data.inventory_label, wait=wait
    )


@router.get("/dr/analyze", tags=["analysis"], status_code=202, responses=_ANALYZE_RESPONSES)
async def get_analyze(
    state: State,
    runbook: Annotated[str, Query(min_length=1, max_length=512, examples=["runbooks/x.md"])],
    inventory: Annotated[str | None, Query(max_length=512)] = None,
    wait: Wait = False,
) -> JSONResponse:
    """Analyze server-side files, given as paths relative to `API_ALLOWED_DIR`."""
    base = Path(state.settings.api_allowed_dir)
    runbook_path = resolve_allowed_path(base, runbook, suffixes=(".md", ".markdown"))
    inventory_path = (
        resolve_allowed_path(base, inventory, suffixes=(".json",)) if inventory else None
    )
    parsed = parse_markdown(read_text_file(runbook_path))
    loaded = load_inventory(inventory_path) if inventory_path else None
    return await _submit(state, parsed, loaded, runbook, inventory, wait=wait)


@router.get(
    "/dr/jobs/{job_id}", response_model=JobView, tags=["analysis"], responses={404: _ERRORS[404]}
)
async def get_job(
    state: State,
    job_id: JobId,
    wait: Wait = False,
) -> JobView:
    """Poll a job; `report` is set once `status` is `succeeded`, `error` once `failed`.

    Jobs no longer in memory (after a restart) are answered from the history.
    """
    job, view = await job_view(state, job_id)
    if wait and job is not None:
        await state.jobs.wait(job, state.settings.api_wait_timeout_seconds)
        view = job.view()
    return view


@router.get(
    "/dr/jobs/{job_id}/report.html",
    response_class=HTMLResponse,
    tags=["analysis"],
    responses={404: _ERRORS[404], 409: {"model": ErrorBody}},
)
async def get_job_report_html(state: State, job_id: JobId) -> HTMLResponse:
    """The finished job's report as a self-contained HTML download (autoescaped)."""
    analysis = await finished_analysis(state, job_id)
    return html_report(analysis.id, analysis.report)


def html_report(analysis_id: str, report: DRReadinessReport) -> HTMLResponse:
    headers = {
        "Content-Disposition": f'attachment; filename="dr-report-{analysis_id}.html"',
        "Content-Security-Policy": REPORT_CSP,
    }
    return HTMLResponse(format_html(report), headers=headers)


async def _submit(
    state: AppState,
    runbook: Runbook,
    inventory: SystemInventory | None,
    runbook_label: str,
    inventory_label: str | None,
    *,
    wait: bool,
) -> JSONResponse:
    job = state.jobs.submit(
        lambda: analyze_runbook(
            runbook,
            inventory,
            llm=state.llm,
            checker=state.checker,
            runbook_label=runbook_label,
            inventory_label=inventory_label,
            knowledge=state.knowledge,
        ),
        runbook=runbook,
        label=runbook_label,
        inventory=inventory,
        inventory_label=inventory_label,
    )
    if wait:
        await state.jobs.wait(job, state.settings.api_wait_timeout_seconds)
        if job.state is JobState.SUCCEEDED and job.report is not None:
            return JSONResponse(job.report.to_json_dict(), status_code=200)
    view = job.view().model_dump(mode="json", by_alias=True)
    return JSONResponse(view, status_code=202, headers={"Location": f"/api/v1/dr/jobs/{job.id}"})
