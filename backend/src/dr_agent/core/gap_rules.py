"""Rule-based gap detection: the checks small local LLMs reliably miss.

These four gap types are computed in code, not asked of the model (Phase 0
finding): OWNER_AMBIGUITY, NO_VALIDATION, MISSING_ROLLBACK, UNVERIFIED_DEPENDENCY.
The LLM analyzer treats these types as rule-owned and never emits them itself.
HISTORICAL gaps (Phase 14) are rule-owned too; they come from `knowledge/rules.py`.
"""

from __future__ import annotations

from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DependencyHealth, Gap, GapType, Severity
from dr_agent.models.runbook import Runbook

RULE_OWNED_GAP_TYPES = frozenset(
    {
        GapType.OWNER_AMBIGUITY,
        GapType.NO_VALIDATION,
        GapType.MISSING_ROLLBACK,
        GapType.UNVERIFIED_DEPENDENCY,
        GapType.HISTORICAL,
    }
)

_AMBIGUOUS_OWNERS = {"team", "tbd", "unknown", "n/a", "someone"}
_ROLLBACK_WORDS = ("rollback", "roll back", "revert")

_UNVERIFIED_SEVERITY = {
    DependencyStatus.DOWN: Severity.HIGH,
    DependencyStatus.UNREACHABLE: Severity.HIGH,
    DependencyStatus.NOT_IN_INVENTORY: Severity.MEDIUM,
}


def compute_rule_gaps(runbook: Runbook, dependency_health: list[DependencyHealth]) -> list[Gap]:
    gaps: list[Gap] = []
    gaps.extend(_owner_ambiguity(runbook))
    gaps.extend(_no_validation(runbook))
    gaps.extend(_missing_rollback(runbook))
    gaps.extend(_unverified_dependencies(dependency_health))
    return gaps


def _owner_ambiguity(runbook: Runbook) -> list[Gap]:
    ambiguous = [
        s.step_number for s in runbook.steps if s.owner.strip().lower() in _AMBIGUOUS_OWNERS
    ]
    if not ambiguous:
        return []
    severity = Severity.HIGH if len(ambiguous) / len(runbook.steps) > 0.5 else Severity.MEDIUM
    joined = ", ".join(str(n) for n in ambiguous)
    return [
        Gap(
            type=GapType.OWNER_AMBIGUITY,
            description=(
                f"Step(s) {joined} have a vague or placeholder owner "
                "instead of a named person or team."
            ),
            severity=severity,
            recommendation="Assign a specific, on-call-reachable owner to each step.",
        )
    ]


def _no_validation(runbook: Runbook) -> list[Gap]:
    missing = [s.step_number for s in runbook.steps if not s.validation_command]
    if not missing:
        return []
    severity = Severity.HIGH if len(missing) / len(runbook.steps) > 0.5 else Severity.MEDIUM
    joined = ", ".join(str(n) for n in missing)
    return [
        Gap(
            type=GapType.NO_VALIDATION,
            description=f"Step(s) {joined} have no validation command to confirm they succeeded.",
            severity=severity,
            recommendation="Add a concrete validation command or check to each recovery step.",
        )
    ]


def _missing_rollback(runbook: Runbook) -> list[Gap]:
    # Checked against the whole document, not just parsed steps: a runbook may
    # describe rollback in a dedicated section that the parser does not turn
    # into `Step` objects (e.g. a "## Rollback" heading).
    raw = runbook.raw_markdown.lower()
    has_rollback = any(word in raw for word in _ROLLBACK_WORDS)
    if has_rollback:
        return []
    return [
        Gap(
            type=GapType.MISSING_ROLLBACK,
            description=(
                "No step describes how to roll back or revert the recovery "
                "procedure if it fails partway through."
            ),
            severity=Severity.HIGH,
            recommendation="Add explicit rollback steps for at least the highest-risk actions.",
        )
    ]


def _unverified_dependencies(dependency_health: list[DependencyHealth]) -> list[Gap]:
    return [
        Gap(
            type=GapType.UNVERIFIED_DEPENDENCY,
            description=f"Dependency '{dep.name}' is {dep.actual_status.value} ({dep.impact}).",
            severity=_UNVERIFIED_SEVERITY[dep.actual_status],
            recommendation=(
                "Confirm the dependency's real status before relying on this runbook, or update it."
            ),
        )
        for dep in dependency_health
        if dep.actual_status in _UNVERIFIED_SEVERITY
    ]
