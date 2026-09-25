"""Builds the user prompt: runbook + validation facts, delimited, plus instructions.

The deterministic facts already computed in `core/` (RTO math, dependency health,
the four rule-checkable gap types) are included so the model reasons on top of
them instead of re-deriving them, and is told which gap types are already covered.

Measured history (Phase 14) goes into a `<history>` block: allow-listed facts
only (`knowledge/prompt_facts.py`), never text from past reports or tools.

Untrusted text is embedded as JSON with `<`, `>` and `&` written as JSON unicode
escapes, so runbook content can never forge a closing `</runbook>` delimiter.
"""

from __future__ import annotations

import json

from pydantic import JsonValue

from dr_agent.core.gap_rules import RULE_OWNED_GAP_TYPES
from dr_agent.models.report import DependencyHealth, Gap, RtoAnalysis
from dr_agent.models.runbook import Runbook

# Markup characters as JSON unicode escapes: still valid JSON, decoding to the same text.
# Recorded with each stored analysis (ADR 0007); bump when the prompt changes.
PROMPT_VERSION = "analysis/2"  # 2: optional <history> block

_MARKUP_ESCAPES = {ord(char): f"\\u{ord(char):04x}" for char in "&<>"}

_EXAMPLE = {
    "stepDependencies": [{"stepNumber": "<step number>", "dependsOn": ["<earlier step number>"]}],
    "singlePointsOfFailure": [
        {
            "description": "<what single person/system/step blocks recovery if it fails>",
            "affectedSteps": ["<step number(s)>"],
            "mitigationSuggestion": "<how to remove the single point of failure>",
        }
    ],
    "gapAnalysis": [
        {
            "type": "MISSING_STEP | VAGUE_INSTRUCTION",
            "description": "<the specific gap, quoting the runbook text it refers to>",
            "severity": "LOW | MEDIUM | HIGH",
            "recommendation": "<the specific fix>",
        }
    ],
    "suggestions": [{"priority": "<1-5>", "title": "<short title>", "detail": "<specific action>"}],
    "summary": "<2-3 plain-language paragraphs about THIS runbook specifically>",
    "riskScore": "<your own integer 0-100>",
}


def build_analysis_prompt(
    runbook: Runbook,
    dependency_health: list[DependencyHealth],
    rto: RtoAnalysis,
    rule_gaps: list[Gap],
    history_facts: dict[str, JsonValue] | None = None,
) -> str:
    runbook_json = prompt_json(_runbook_for_prompt(runbook))
    validation_json = prompt_json(
        {
            "dependencyHealth": [d.to_json_dict() for d in dependency_health],
            "rtoAnalysis": rto.to_json_dict(),
            "rulesAlreadyChecked": [g.to_json_dict() for g in rule_gaps],
        }
    )
    already_covered = ", ".join(sorted(t.value for t in RULE_OWNED_GAP_TYPES))
    history = (
        f"<history>\n{prompt_json(history_facts)}\n</history>\n\n"
        "The <history> block holds facts measured from past analyses and live runs "
        "of this service (step outcomes, measured minutes, dependency status counts). "
        "Use them as evidence where relevant; HISTORICAL gaps derived from them are "
        "already in rulesAlreadyChecked.\n\n"
        if history_facts is not None
        else ""
    )

    return (
        "Analyze this DR runbook using the parsed data and validation results below.\n\n"
        f"<runbook>\n{runbook_json}\n</runbook>\n\n"
        f"<validation>\n{validation_json}\n</validation>\n\n"
        f"{history}"
        "Produce these sections:\n"
        "- stepDependencies: for each step that has an implicit dependency on an "
        "earlier step (beyond what is already listed), infer it from the action text.\n"
        "- singlePointsOfFailure: people, systems or steps whose failure blocks recovery "
        "with no alternative.\n"
        f"- gapAnalysis: gaps of type MISSING_STEP or VAGUE_INSTRUCTION only. Types "
        f"{already_covered} are already checked by rules above (see rulesAlreadyChecked) "
        "-- do not repeat them.\n"
        "- suggestions: up to 5, ranked by priority (1 = most urgent).\n"
        "- summary: 2-3 paragraphs, readable by a non-technical reader.\n"
        "- riskScore: your own 0-100 judgement, informed by rtoAnalysis and "
        "dependencyHealth above but not a mechanical copy of them.\n\n"
        "The JSON below shows the SHAPE of the reply only. Every value in angle "
        "brackets is a placeholder, not real content -- replace all of them with "
        "your own findings about the <runbook> above. Never copy any wording or "
        "numbers from this example into your answer:\n"
        f"{json.dumps(_EXAMPLE, indent=2)}"
    )


def prompt_json(data: object) -> str:
    """JSON with markup characters escaped: still valid JSON, but no tag can appear in it."""
    text = json.dumps(data, indent=2)
    return text.translate(_MARKUP_ESCAPES)


def _runbook_for_prompt(runbook: Runbook) -> dict[str, object]:
    data = runbook.to_json_dict()
    data.pop("rawMarkdown", None)
    return data
