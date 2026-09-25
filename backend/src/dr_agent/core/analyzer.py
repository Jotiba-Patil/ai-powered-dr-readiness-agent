"""Orchestrates one analysis: rule-based facts + LLM reasoning -> DRReadinessReport.

Deterministic facts (RTO, four gap types, risk-score fallback) are always
computed. The LLM is then asked for the reasoning-heavy sections; on any
`AnalysisError` (malformed output surviving its own retries, or a transport
failure surviving the provider's retries) the report degrades gracefully to
rule-based results only, per `llm-and-security` and `llm-structured-output`.

With a `ServiceHistory` (Phase 14, ADR 0009) the history rules add HISTORICAL
gaps next to the other rule gaps, the measured facts go into the prompt as a
`<history>` block (allow-listed fields only) and the report carries them.

`run_analysis()` takes an already-parsed `Runbook` and already-computed
`DependencyHealth`, not file paths -- it is the Phase 4 building block, not
the Phase 5 `analyze_runbook()` service function that will wrap parsing and
health checks around this for the CLI and API to share.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from dr_agent.core.dependency_graph import merge_depends_on
from dr_agent.core.execution_plan import compute_execution_plan
from dr_agent.core.gap_rules import RULE_OWNED_GAP_TYPES, compute_rule_gaps
from dr_agent.core.risk_score import compute_rule_based_score
from dr_agent.core.rto_analysis import compute_rto_analysis
from dr_agent.knowledge.prompt_facts import history_prompt_facts
from dr_agent.knowledge.rules import compute_history_gaps
from dr_agent.llm.base import LLMProvider
from dr_agent.llm.parse import get_llm_analysis
from dr_agent.llm.prompts.analysis import build_analysis_prompt
from dr_agent.llm.prompts.system import SYSTEM_PROMPT
from dr_agent.llm.schemas import LlmAnalysis
from dr_agent.models.insights import ServiceHistory
from dr_agent.models.report import (
    DependencyHealth,
    DRReadinessReport,
    Gap,
    ReportMeta,
    ServiceSummary,
)
from dr_agent.models.runbook import Runbook
from dr_agent.utils.errors import AnalysisError
from dr_agent.utils.timing import Stopwatch

_DEGRADED_SUMMARY = (
    "AI analysis was unavailable for this run. The figures below are rule-based "
    "only: RTO math, dependency health and the four automatically-checkable gap "
    "types. Single points of failure, additional gaps and suggestions require a "
    "working LLM provider and are not included."
)


async def run_analysis(
    runbook: Runbook,
    dependency_health: list[DependencyHealth],
    llm: LLMProvider,
    *,
    runbook_file: str,
    inventory_file: str,
    agent_version: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    timer: Callable[[], float] = time.perf_counter,
    history: ServiceHistory | None = None,
    history_in_prompt: bool = True,
) -> DRReadinessReport:
    watch = Stopwatch(timer)

    rto = compute_rto_analysis(runbook)
    rule_gaps = compute_rule_gaps(runbook, dependency_health)
    if history is not None:
        rule_gaps += compute_history_gaps(history)
    facts = history_prompt_facts(history) if history and history_in_prompt else None
    rule_score = compute_rule_based_score(rto, rule_gaps, dependency_health)

    llm_analysis: LlmAnalysis | None = None
    ai_note: str | None = None
    try:
        prompt = build_analysis_prompt(runbook, dependency_health, rto, rule_gaps, facts)
        llm_analysis = await get_llm_analysis(llm, system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
    except AnalysisError as exc:
        ai_note = f"AI analysis unavailable: {exc.message}"

    inferred = llm_analysis.step_dependencies if llm_analysis else []
    execution_plan = compute_execution_plan(
        runbook.steps,
        merge_depends_on(runbook.steps, ((d.step_number, d.depends_on) for d in inferred)),
    )

    return DRReadinessReport(
        meta=ReportMeta(
            analyzed_at=clock(),
            runbook_file=runbook_file,
            inventory_file=inventory_file,
            agent_version=agent_version,
            analysis_time_ms=watch.elapsed_ms,
        ),
        service_summary=ServiceSummary(
            name=runbook.service_name,
            owner=runbook.system_owner,
            stated_rto=runbook.rto_minutes,
            stated_rpo=runbook.rpo_minutes,
        ),
        risk_score=llm_analysis.risk_score if llm_analysis else rule_score,
        rto_analysis=rto,
        dependency_health=dependency_health,
        single_points_of_failure=llm_analysis.single_points_of_failure if llm_analysis else [],
        gap_analysis=rule_gaps + _additive_llm_gaps(llm_analysis),
        execution_plan=execution_plan,
        suggestions=llm_analysis.suggestions if llm_analysis else [],
        summary=llm_analysis.summary if llm_analysis else _DEGRADED_SUMMARY,
        ai_analysis_available=llm_analysis is not None,
        ai_note=ai_note,
        historical_insights=history,
    )


def _additive_llm_gaps(llm_analysis: LlmAnalysis | None) -> list[Gap]:
    if llm_analysis is None:
        return []
    return [g for g in llm_analysis.gap_analysis if g.type not in RULE_OWNED_GAP_TYPES]
