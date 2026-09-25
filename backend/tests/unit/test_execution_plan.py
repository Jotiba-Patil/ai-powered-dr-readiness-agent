from dr_agent.core.execution_plan import compute_execution_plan
from dr_agent.models.runbook import Step


def _step(number: int, minutes: float) -> Step:
    return Step(
        step_number=number, action=f"Step {number}", owner="Dana", estimated_minutes=minutes
    )


def test_no_dependencies_puts_every_step_in_one_phase() -> None:
    steps = [_step(1, 5), _step(2, 10), _step(3, 3)]
    plan = compute_execution_plan(steps, {1: set(), 2: set(), 3: set()})
    assert len(plan) == 1
    assert plan[0].steps == [1, 2, 3]
    assert plan[0].estimated_minutes == 10  # slowest step, they run in parallel
    assert "initial phase" in plan[0].gate


def test_linear_chain_produces_one_phase_per_step() -> None:
    steps = [_step(1, 5), _step(2, 10), _step(3, 3)]
    plan = compute_execution_plan(steps, {1: set(), 2: {1}, 3: {2}})
    assert [phase.steps for phase in plan] == [[1], [2], [3]]
    assert [phase.phase for phase in plan] == [1, 2, 3]


def test_steps_with_satisfied_dependencies_share_a_phase() -> None:
    # 1 has no deps; 2 and 3 both depend only on 1 -> phase 1 = [1], phase 2 = [2, 3]
    steps = [_step(1, 5), _step(2, 10), _step(3, 8)]
    plan = compute_execution_plan(steps, {1: set(), 2: {1}, 3: {1}})
    assert plan[0].steps == [1]
    assert plan[1].steps == [2, 3]
    assert plan[1].estimated_minutes == 10


def test_gate_names_the_required_upstream_steps() -> None:
    steps = [_step(1, 5), _step(2, 10)]
    plan = compute_execution_plan(steps, {1: set(), 2: {1}})
    assert plan[1].gate == "step(s) 1 complete"


def test_cycle_falls_back_to_a_single_final_phase_instead_of_looping() -> None:
    steps = [_step(1, 5), _step(2, 10), _step(3, 3)]
    # 1 depends on 3 depends on 2 depends on 1: a cycle with no way to start.
    plan = compute_execution_plan(steps, {1: {3}, 2: {1}, 3: {2}})
    assert len(plan) == 1
    assert plan[0].steps == [1, 2, 3]
