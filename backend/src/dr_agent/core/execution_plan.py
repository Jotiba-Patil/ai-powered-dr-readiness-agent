"""Deterministic execution phases from step `dependsOn` (parser + AI-inferred).

Kahn's-algorithm layering: phase 1 holds every step with no unresolved
dependency, phase 2 the steps whose dependencies are all satisfied by phase 1,
and so on. Steps that share a phase can run in parallel, so a phase's duration
is the slowest step in it, not the sum. If the merged dependency graph has a
cycle (always possible once AI-inferred edges are added), every step still
stuck after layering is dropped into one final phase together rather than
looping forever.
"""

from __future__ import annotations

from dr_agent.models.report import ExecutionPhase
from dr_agent.models.runbook import Step


def compute_execution_plan(
    steps: list[Step], depends_on: dict[int, set[int]]
) -> list[ExecutionPhase]:
    steps_by_number = {step.step_number: step for step in steps}
    remaining = set(steps_by_number)
    placed: set[int] = set()
    phases: list[ExecutionPhase] = []

    while remaining:
        ready = {number for number in remaining if depends_on.get(number, set()) <= placed}
        if not ready:
            ready = set(remaining)  # cycle: flush everything left into one final phase

        phase_steps = sorted(ready)
        phase_minutes = max(steps_by_number[n].estimated_minutes for n in phase_steps)
        phases.append(
            ExecutionPhase(
                phase=len(phases) + 1,
                steps=phase_steps,
                estimated_minutes=phase_minutes,
                gate=_gate(phases, phase_steps, depends_on),
            )
        )
        placed |= ready
        remaining -= ready

    return phases


def _gate(
    prior_phases: list[ExecutionPhase], phase_steps: list[int], depends_on: dict[int, set[int]]
) -> str:
    if not prior_phases:
        return "none: initial phase, no prerequisites"
    required = sorted({dep for number in phase_steps for dep in depends_on.get(number, set())})
    if not required:
        return "none: no unresolved dependencies"
    joined = ", ".join(str(number) for number in required)
    return f"step(s) {joined} complete"
