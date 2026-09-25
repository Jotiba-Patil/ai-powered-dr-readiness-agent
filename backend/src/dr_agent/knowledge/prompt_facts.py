"""The only history that may reach an LLM prompt (ADR 0009): an explicit allow-list.

Numbers, enum values, timestamps, step numbers and identifiers that already come
from the runbook or inventory. Fields are copied one by one, so a field added
to `ServiceHistory` later never reaches a prompt by accident; a test checks the
allowed key set.
"""

from __future__ import annotations

from pydantic import JsonValue

from dr_agent.models.insights import ServiceHistory

STEP_FIELDS = (
    "stepNumber",
    "targetSystem",
    "estimatedMinutes",
    "liveRuns",
    "succeeded",
    "failed",
    "rolledBack",
    "skipped",
    "manualDone",
    "unknown",
    "retries",
    "medianActiveMinutes",
    "maxActiveMinutes",
    "medianElapsedMinutes",
)
EXECUTION_FIELDS = ("state", "startedAt", "elapsedMinutes", "statedRtoMinutes")
DEPENDENCY_FIELDS = ("name", "analyses", "up", "down", "unreachable", "notInInventory")
TOP_FIELDS = ("analysesConsidered", "liveRuns", "dryRuns", "riskScores")


def _pick(data: dict[str, JsonValue], fields: tuple[str, ...]) -> dict[str, JsonValue]:
    return {name: data[name] for name in fields if name in data}


def history_prompt_facts(history: ServiceHistory) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = history.model_dump(mode="json", by_alias=True)
    facts = _pick(data, TOP_FIELDS)
    facts["steps"] = [
        _pick(s.model_dump(mode="json", by_alias=True), STEP_FIELDS) for s in history.steps
    ]
    facts["executions"] = [
        _pick(e.model_dump(mode="json", by_alias=True), EXECUTION_FIELDS)
        for e in history.executions
    ]
    facts["dependencies"] = [
        _pick(d.model_dump(mode="json", by_alias=True), DEPENDENCY_FIELDS)
        for d in history.dependencies
    ]
    return facts
