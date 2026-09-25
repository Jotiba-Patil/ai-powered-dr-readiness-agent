from dr_agent.core.gap_rules import compute_rule_gaps
from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DependencyHealth, GapType, Severity
from dr_agent.models.runbook import Runbook, Step


def _runbook(
    steps: list[Step] | None = None, *, raw_markdown: str = "# Svc\n\n## Recovery Steps\n"
) -> Runbook:
    return Runbook(
        service_name="Svc",
        system_owner="Dana",
        rto_minutes=60,
        rpo_minutes=15,
        raw_markdown=raw_markdown,
        steps=steps or [Step(step_number=1, action="Do it", owner="Dana", estimated_minutes=5)],
    )


def _dep(name: str, status: DependencyStatus) -> DependencyHealth:
    return DependencyHealth(name=name, actual_status=status, impact="not referenced")


def test_no_gaps_for_a_clean_runbook() -> None:
    steps = [
        Step(
            step_number=1,
            action="Do it",
            owner="Alice",
            estimated_minutes=5,
            validation_command="curl -f https://x",
        )
    ]
    runbook = _runbook(steps, raw_markdown="# Svc\n\nOn failure, revert traffic.\n")
    gaps = compute_rule_gaps(runbook, [])
    assert gaps == []


def test_ambiguous_owner_is_flagged() -> None:
    steps = [Step(step_number=1, action="Do it", owner="team", estimated_minutes=5)]
    runbook = _runbook(steps)
    gaps = compute_rule_gaps(runbook, [])
    owner_gaps = [g for g in gaps if g.type is GapType.OWNER_AMBIGUITY]
    assert len(owner_gaps) == 1
    assert "1" in owner_gaps[0].description


def test_missing_validation_is_flagged() -> None:
    runbook = _runbook()
    gaps = compute_rule_gaps(runbook, [])
    assert any(g.type is GapType.NO_VALIDATION for g in gaps)


def test_missing_rollback_is_flagged_when_document_never_mentions_it() -> None:
    runbook = _runbook(raw_markdown="# Svc\n\n## Recovery Steps\nRestart the service.\n")
    gaps = compute_rule_gaps(runbook, [])
    assert any(g.type is GapType.MISSING_ROLLBACK for g in gaps)


def test_rollback_section_outside_parsed_steps_still_satisfies_the_check() -> None:
    runbook = _runbook(raw_markdown="# Svc\n\n## Rollback\nRevert DNS to primary.\n")
    gaps = compute_rule_gaps(runbook, [])
    assert not any(g.type is GapType.MISSING_ROLLBACK for g in gaps)


def test_unverified_dependency_flags_down_and_unreachable_and_not_in_inventory() -> None:
    dep_health = [
        _dep("db", DependencyStatus.DOWN),
        _dep("cache", DependencyStatus.UNREACHABLE),
        _dep("queue", DependencyStatus.NOT_IN_INVENTORY),
        _dep("dns", DependencyStatus.UP),
    ]
    runbook = _runbook(raw_markdown="# Svc\n\nRevert on failure.\n")
    gaps = compute_rule_gaps(runbook, dep_health)
    unverified = {
        g.description: g.severity for g in gaps if g.type is GapType.UNVERIFIED_DEPENDENCY
    }
    assert len(unverified) == 3
    assert any(sev is Severity.HIGH for sev in unverified.values())
    assert any(sev is Severity.MEDIUM for sev in unverified.values())


def test_severity_escalates_when_more_than_half_the_steps_are_affected() -> None:
    steps = [
        Step(step_number=1, action="a", owner="team", estimated_minutes=5),
        Step(step_number=2, action="b", owner="team", estimated_minutes=5),
        Step(step_number=3, action="c", owner="Alice", estimated_minutes=5),
    ]
    runbook = _runbook(steps)
    gaps = compute_rule_gaps(runbook, [])
    owner_gap = next(g for g in gaps if g.type is GapType.OWNER_AMBIGUITY)
    assert owner_gap.severity is Severity.HIGH
