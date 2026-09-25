from dr_agent.core.dependency_graph import merge_depends_on
from dr_agent.models.runbook import Step


def _step(number: int, depends_on: list[int] | None = None) -> Step:
    return Step(
        step_number=number,
        action=f"step {number}",
        owner="Ann",
        estimated_minutes=5,
        depends_on=depends_on or [],
    )


def test_explicit_dependencies_only() -> None:
    steps = [_step(1), _step(2, [1])]
    assert merge_depends_on(steps) == {1: set(), 2: {1}}


def test_inferred_edges_are_added_and_invalid_ones_dropped() -> None:
    steps = [_step(1), _step(2), _step(3, [1])]
    inferred = [(3, [2, 3, 99]), (2, [1]), (42, [1])]
    assert merge_depends_on(steps, inferred) == {1: set(), 2: {1}, 3: {1, 2}}
