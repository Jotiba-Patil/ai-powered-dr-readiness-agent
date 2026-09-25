"""Analysis history routes (design analysis-history section 6, ADR 0007 and 0008).

Every route returns `403 HISTORY_DISABLED` while `HISTORY_ENABLED=false`. The
stored runbook is only ever served as a plain-text download, never rendered.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, PlainTextResponse

from dr_agent.api.deps import AppState, get_state
from dr_agent.api.routes import html_report
from dr_agent.api.schemas import ErrorBody
from dr_agent.api.schemas_execution import AuditView, ExecutionSummary
from dr_agent.api.schemas_history import AnalysisDetail, AnalysisPage, StoredExecution
from dr_agent.execution.audit import verify_chain
from dr_agent.history.models import MAX_PAGE, AnalysisQuery
from dr_agent.history.service import History
from dr_agent.knowledge.service import KnowledgeBase
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.report import RiskLevel
from dr_agent.utils.errors import HistoryDisabledError

router = APIRouter(prefix="/api/v1", tags=["history"])

State = Annotated[AppState, Depends(get_state)]
AnalysisId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorBody} for code in (403, 404, 409, 422)
}


def get_history(state: State) -> History:
    if state.history is None:
        raise HistoryDisabledError("analysis history is disabled (HISTORY_ENABLED)")
    return state.history


HistoryDep = Annotated[History, Depends(get_history)]
ServiceName = Annotated[str, PathParam(min_length=1, max_length=200)]


def get_knowledge(state: State) -> KnowledgeBase:
    if state.knowledge is None:
        raise HistoryDisabledError(
            "the knowledge base is disabled (HISTORY_ENABLED or KNOWLEDGE_ENABLED)"
        )
    return state.knowledge


KnowledgeDep = Annotated[KnowledgeBase, Depends(get_knowledge)]


@router.get("/analyses", response_model=AnalysisPage, responses=ERRORS)
async def list_analyses(
    history: HistoryDep,
    service: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    risk_level: Annotated[RiskLevel | None, Query(alias="riskLevel")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 20,
    before: Annotated[datetime | None, Query(description="`nextBefore` of the last page")] = None,
) -> AnalysisPage:
    """Stored analyses, newest first."""
    query = AnalysisQuery(service=service, risk_level=risk_level, limit=limit, before=before)
    items = await history.store.list_page(query)
    next_before = items[-1].completed_at if len(items) == limit else None
    return AnalysisPage(items=items, next_before=next_before)


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail, responses=ERRORS)
async def get_analysis(analysis_id: AnalysisId, history: HistoryDep) -> AnalysisDetail:
    record = await history.store.get(analysis_id)
    return AnalysisDetail(
        summary=await history.store.summary(analysis_id),
        report=record.report,
        provenance=record.provenance,
        stale=history.is_stale(record.completed_at),
    )


@router.get("/analyses/{analysis_id}/runbook", response_class=PlainTextResponse, responses=ERRORS)
async def get_analysis_runbook(analysis_id: AnalysisId, history: HistoryDep) -> PlainTextResponse:
    """The runbook Markdown exactly as analyzed, as a text download."""
    record = await history.store.get(analysis_id)
    headers = {"Content-Disposition": f'attachment; filename="runbook-{record.id}.md"'}
    return PlainTextResponse(record.runbook.raw_markdown, headers=headers)


@router.get("/analyses/{analysis_id}/report.html", response_class=HTMLResponse, responses=ERRORS)
async def get_analysis_report_html(analysis_id: AnalysisId, history: HistoryDep) -> HTMLResponse:
    record = await history.store.get(analysis_id)
    return html_report(record.id, record.report)


@router.get(
    "/analyses/{analysis_id}/executions",
    response_model=list[ExecutionSummary],
    responses=ERRORS,
)
async def get_analysis_executions(
    analysis_id: AnalysisId, history: HistoryDep
) -> list[ExecutionSummary]:
    """Executions created from this analysis (also readable while execution is off)."""
    await history.store.summary(analysis_id)  # 404 for an unknown id
    return [ExecutionSummary.of(e) for e in await history.executions(analysis_id)]


@router.get(
    "/analyses/{analysis_id}/executions/{execution_id}",
    response_model=StoredExecution,
    responses=ERRORS,
)
async def get_analysis_execution(
    analysis_id: AnalysisId, execution_id: AnalysisId, history: HistoryDep
) -> StoredExecution:
    """One execution of this analysis with its steps and its verified audit log (read-only)."""
    execution, events = await history.execution(analysis_id, execution_id)
    audit = AuditView(events=events, verification=verify_chain(execution_id, events))
    return StoredExecution(execution=execution, audit=audit)


@router.delete("/analyses/{analysis_id}", status_code=204, responses=ERRORS)
async def delete_analysis(analysis_id: AnalysisId, history: HistoryDep) -> Response:
    """`409` when executions refer to it: their audit trail must keep its source."""
    await history.store.delete(analysis_id)
    return Response(status_code=204)


@router.get("/services/{service_name}/history", response_model=ServiceHistory, responses=ERRORS)
async def get_service_history(service_name: ServiceName, knowledge: KnowledgeDep) -> ServiceHistory:
    """Measured facts from this service's stored analyses and finished live runs (ADR 0009).

    Steps are keyed by fingerprint; a report's `historicalInsights` has them matched
    to that runbook's step numbers instead.
    """
    return await knowledge.service_history(service_name)
