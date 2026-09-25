from dr_agent.core.rto_analysis import compute_rto_analysis
from dr_agent.models.runbook import Runbook, Step


def _runbook(rto_minutes: float, step_minutes: list[float]) -> Runbook:
    return Runbook(
        service_name="Svc",
        system_owner="Dana",
        rto_minutes=rto_minutes,
        rpo_minutes=15,
        raw_markdown="# Svc",
        steps=[
            Step(step_number=i + 1, action=f"Step {i + 1}", owner="Dana", estimated_minutes=m)
            for i, m in enumerate(step_minutes)
        ],
    )


def test_feasible_when_total_within_rto() -> None:
    runbook = _runbook(60, [5, 15, 10, 15, 10])
    result = compute_rto_analysis(runbook)
    assert result.feasible is True
    assert result.total_estimated_minutes == 55
    assert result.buffer_minutes == 5
    assert result.bottleneck_steps == []


def test_infeasible_when_total_exceeds_rto() -> None:
    runbook = _runbook(15, [20, 20, 15, 5])
    result = compute_rto_analysis(runbook)
    assert result.feasible is False
    assert result.buffer_minutes == -45


def test_bottleneck_steps_are_the_minimal_set_that_closes_the_gap() -> None:
    # total 60, rto 45 -> overage 15. Longest step (30) alone closes the gap.
    runbook = _runbook(45, [30, 10, 10, 10])
    result = compute_rto_analysis(runbook)
    assert result.bottleneck_steps == [1]


def test_bottleneck_steps_accumulate_until_overage_is_covered() -> None:
    # total 40, rto 10 -> overage 30. Steps sorted desc: 15, 10, 10, 5.
    # 15 alone (15 >= 30)? No. 15+10=25 < 30. 15+10+10=35 >= 30 -> steps 1,2,3.
    runbook = _runbook(10, [15, 10, 10, 5])
    result = compute_rto_analysis(runbook)
    assert result.bottleneck_steps == [1, 2, 3]


def test_exact_match_is_feasible() -> None:
    runbook = _runbook(30, [10, 10, 10])
    result = compute_rto_analysis(runbook)
    assert result.feasible is True
    assert result.buffer_minutes == 0
