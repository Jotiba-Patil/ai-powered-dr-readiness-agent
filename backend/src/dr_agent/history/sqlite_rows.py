"""SQL and row conversions for the `analyses` table (migration 2, ADR 0007).

The parsed runbook is stored without its Markdown, which has its own column
(ADR 0008), and is put back together on load. Everything read back is
validated again, like any other external input.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import ValidationError as PydanticValidationError

from dr_agent.execution.canonical import sha256_hex
from dr_agent.history.models import AnalysisQuery, AnalysisRecord, AnalysisSummary
from dr_agent.storage.sqlite import timestamp
from dr_agent.utils.errors import ValidationError

Row = Sequence[object]

INSERT_ANALYSIS = (
    "INSERT INTO analyses (id, service_name, owner, created_at, completed_at, source, "
    "runbook_label, runbook_sha256, runbook_markdown, inventory_label, inventory_json, "
    "risk_score, risk_level, rto_feasible, ai_analysis_available, llm_provider, llm_model, "
    "prompt_version, agent_version, runbook_json, report_json) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
RECORD_COLUMNS = (
    "id, source, created_at, completed_at, runbook_label, runbook_markdown, runbook_json, "
    "inventory_label, inventory_json, report_json, llm_provider, llm_model, prompt_version, "
    "agent_version"
)
# Constant column list; every value is a bound parameter.
SELECT_RECORD = f"SELECT {RECORD_COLUMNS} FROM analyses WHERE id = ?"  # noqa: S608
_SUMMARY = (
    "SELECT a.id, a.service_name, a.owner, a.source, a.created_at, a.completed_at, "
    "a.runbook_label, a.inventory_label, a.risk_score, a.risk_level, a.rto_feasible, "
    "a.ai_analysis_available, "
    "(SELECT COUNT(*) FROM executions e WHERE e.analysis_id = a.id) FROM analyses a"
)
SELECT_SUMMARY = f"{_SUMMARY} WHERE a.id = ?"
COUNT_EXECUTIONS = "SELECT COUNT(*) FROM executions WHERE analysis_id = ?"
DELETE_ANALYSIS = "DELETE FROM analyses WHERE id = ?"
PRUNE = (
    "DELETE FROM analyses WHERE completed_at < ? "
    "AND NOT EXISTS (SELECT 1 FROM executions e WHERE e.analysis_id = analyses.id)"
)
_SUMMARY_FIELDS = (
    "id",
    "service_name",
    "owner",
    "source",
    "created_at",
    "completed_at",
    "runbook_label",
    "inventory_label",
    "risk_score",
    "risk_level",
    "rto_feasible",
    "ai_analysis_available",
    "execution_count",
)


def record_row(record: AnalysisRecord) -> tuple[object, ...]:
    runbook, report = record.runbook, record.report
    return (
        record.id,
        runbook.service_name,
        runbook.system_owner,
        timestamp(record.created_at),
        timestamp(record.completed_at),
        record.source.value,
        record.runbook_label,
        sha256_hex(runbook.raw_markdown),
        runbook.raw_markdown,
        record.inventory_label,
        record.inventory.model_dump_json(by_alias=True) if record.inventory else None,
        report.risk_score,
        report.risk_level.value,
        int(report.rto_analysis.feasible),
        int(report.ai_analysis_available),
        record.provenance.llm_provider,
        record.provenance.llm_model,
        record.provenance.prompt_version,
        record.provenance.agent_version,
        runbook.model_dump_json(by_alias=True, exclude={"raw_markdown"}),
        report.model_dump_json(by_alias=True),
    )


def record_from_row(row: Row) -> AnalysisRecord:
    (id_, source, created, completed, label, markdown, runbook_json, inventory_label) = row[:8]
    inventory_json, report_json, provider, model, prompt_version, agent_version = row[8:]
    try:
        runbook = json.loads(str(runbook_json)) | {"rawMarkdown": markdown}
        return AnalysisRecord.model_validate(
            {
                "id": id_,
                "source": source,
                "createdAt": created,
                "completedAt": completed,
                "runbookLabel": label,
                "runbook": runbook,
                "inventoryLabel": inventory_label,
                "inventory": json.loads(str(inventory_json)) if inventory_json else None,
                "report": json.loads(str(report_json)),
                "provenance": {
                    "llmProvider": provider,
                    "llmModel": model,
                    "promptVersion": prompt_version,
                    "agentVersion": agent_version,
                },
            }
        )
    except (PydanticValidationError, json.JSONDecodeError) as exc:
        raise ValidationError("stored analysis is invalid", details={"id": id_}) from exc


def summary_from_row(row: Row) -> AnalysisSummary:
    data = dict(zip(_SUMMARY_FIELDS, row, strict=True))
    data["rto_feasible"] = bool(data["rto_feasible"])
    data["ai_analysis_available"] = bool(data["ai_analysis_available"])
    return AnalysisSummary.model_validate(data)


def page_sql(query: AnalysisQuery) -> tuple[str, list[object]]:
    """Filters, newest first, keyset pagination on the completion time."""
    where: list[str] = []
    params: list[object] = []
    if query.service is not None:
        where.append("a.service_name = ?")
        params.append(query.service)
    if query.risk_level is not None:
        where.append("a.risk_level = ?")
        params.append(query.risk_level.value)
    if query.before is not None:
        where.append("a.completed_at < ?")
        params.append(timestamp(query.before))
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    params.append(query.limit)
    return f"{_SUMMARY}{clause} ORDER BY a.completed_at DESC, a.id DESC LIMIT ?", params
