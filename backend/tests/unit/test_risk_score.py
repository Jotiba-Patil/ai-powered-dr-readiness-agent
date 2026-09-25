from dr_agent.core.risk_score import compute_rule_based_score
from dr_agent.models.inventory import DependencyStatus
from dr_agent.models.report import DependencyHealth, Gap, GapType, RtoAnalysis, Severity


def _rto(feasible: bool, buffer_minutes: float = 0, stated_rto: float = 60) -> RtoAnalysis:
    return RtoAnalysis(
        feasible=feasible,
        total_estimated_minutes=max(0.0, stated_rto - buffer_minutes),
        stated_rto_minutes=stated_rto,
        buffer_minutes=buffer_minutes,
    )


def _gap(severity: Severity) -> Gap:
    return Gap(type=GapType.NO_VALIDATION, description="d", severity=severity, recommendation="r")


def _dep(status: DependencyStatus) -> DependencyHealth:
    return DependencyHealth(name="db", actual_status=status, impact="i")


def test_clean_runbook_scores_zero() -> None:
    score = compute_rule_based_score(_rto(True, buffer_minutes=5), [], [])
    assert score == 0


def test_infeasible_rto_adds_a_base_penalty() -> None:
    score = compute_rule_based_score(_rto(False, buffer_minutes=-1, stated_rto=100), [], [])
    assert score >= 30


def test_full_overage_adds_the_maximum_rto_penalty() -> None:
    score = compute_rule_based_score(_rto(False, buffer_minutes=-100, stated_rto=100), [], [])
    assert score == 50  # base 30 + max extra 20, ratio clamped to 1.0


def test_gap_severity_adds_points() -> None:
    low = compute_rule_based_score(_rto(True), [_gap(Severity.LOW)], [])
    medium = compute_rule_based_score(_rto(True), [_gap(Severity.MEDIUM)], [])
    high = compute_rule_based_score(_rto(True), [_gap(Severity.HIGH)], [])
    assert low < medium < high


def test_unhealthy_dependencies_add_points() -> None:
    up_only = compute_rule_based_score(_rto(True), [], [_dep(DependencyStatus.UP)])
    down = compute_rule_based_score(_rto(True), [], [_dep(DependencyStatus.DOWN)])
    assert up_only == 0
    assert down > up_only


def test_score_is_clamped_to_100() -> None:
    many_high_gaps = [_gap(Severity.HIGH) for _ in range(20)]
    score = compute_rule_based_score(
        _rto(False, buffer_minutes=-1000, stated_rto=10), many_high_gaps, []
    )
    assert score == 100


def test_score_never_goes_below_zero() -> None:
    score = compute_rule_based_score(_rto(True, buffer_minutes=999), [], [])
    assert score == 0
