"""Planner: phases from the shared dependency graph, and step classification (design 4.2)."""

from datetime import UTC, datetime

from exec_support import OPERATOR, drsim_catalog, drsim_policy, executable_runbook

from dr_agent.core.parser import parse_runbook
from dr_agent.execution.audit import AuditEvent, verify_chain
from dr_agent.execution.canonical import call_hash, sha256_hex
from dr_agent.execution.models import CallSource, Execution, ExecutionMode, RiskClass, StepState
from dr_agent.execution.planner import plan_execution
from dr_agent.execution.policy import index_catalog
from dr_agent.models.runbook import Runbook

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _plan(
    runbook: Runbook, inferred: list[tuple[int, list[int]]] | None = None
) -> tuple[Execution, list[AuditEvent]]:
    return plan_execution(
        runbook,
        policy=drsim_policy(),
        catalog=index_catalog(drsim_catalog()),
        execution_id="exec-1",
        mode=ExecutionMode.DRY_RUN,
        started_by=OPERATOR,
        runbook_label="estimate-service-executable.md",
        now=NOW,
        inferred=inferred or [],
    )


def test_executable_sample_is_fully_approvable() -> None:
    runbook = executable_runbook()
    execution, events = _plan(runbook)
    assert execution.runbook_sha256 == sha256_hex(runbook.raw_markdown)
    assert [(r.step_number, r.phase) for r in execution.steps] == [
        (1, 1),
        (2, 1),
        (3, 2),
        (4, 3),
        (5, 4),
    ]
    assert all(r.state is StepState.AWAITING_APPROVAL for r in execution.steps)
    assert all(r.waiting_since == NOW for r in execution.steps)
    risks = {r.step_number: r.call.risk_class for r in execution.steps if r.call}
    assert risks == {
        1: RiskClass.READ,
        2: RiskClass.WRITE,
        3: RiskClass.DESTRUCTIVE,
        4: RiskClass.WRITE,
        5: RiskClass.DESTRUCTIVE,
    }
    step2 = execution.step(2)
    assert step2.call is not None
    assert step2.call.source is CallSource.ANNOTATED
    assert step2.call.call_hash == call_hash(
        step2.call.server, step2.call.tool, step2.call.arguments
    )
    assert step2.verify is not None
    assert step2.rollback is not None
    assert step2.rollback.risk_class is RiskClass.WRITE
    assert execution.step(5).depends_on == [2, 4]
    assert [e.type for e in events] == ["execution_created"] + ["step_state"] * 5
    assert events[0].payload["phases"] == 4
    assert verify_chain("exec-1", events).valid
    assert execution.audit_head == events[-1].hash


def test_unannotated_steps_become_manual() -> None:
    runbook = parse_runbook(
        (executable_runbook().raw_markdown.split("## Recovery Steps")[0])
        + "## Recovery Steps\n\n1. Page the DBA. Owner: Ann. 5 min.\n"
    )
    execution, _ = _plan(runbook)
    run = execution.steps[0]
    assert run.state is StepState.AWAITING_MANUAL
    assert run.call is None
    assert run.summary == "no tool annotation: manual step"


def test_annotations_failing_policy_need_review() -> None:
    runbook = parse_runbook(
        "# Svc\n\n**Owner:** Ann\n**RTO:** 30 min\n**RPO:** 5 min\n\n## Recovery Steps\n\n"
        "1. Wipe it. Owner: Ann. 5 min.\n"
        "   - Tool: `drsim/drop_database {}`\n"
        "2. Restart. Owner: Ann. 5 min.\n"
        '   - Tool: `drsim/k8s_rollout_restart {"deployment": "api", "region": "mars"}`\n'
        "3. Warm. Owner: Ann. 5 min.\n"
        '   - Tool: `drsim/cache_ping {"cache": "c"}`\n'
        '   - Verify-Tool: `drsim/cache_warm_from_snapshot {"cache": "c", "snapshot": "s"}`\n'
    )
    execution, _ = _plan(runbook)
    assert all(r.state is StepState.PROPOSED for r in execution.steps)
    errors = {r.step_number: r.policy_errors for r in execution.steps}
    assert "not allow-listed" in errors[1][0]
    assert errors[2][0].startswith("main: drsim/k8s_rollout_restart is not allowed")
    assert errors[3] == [
        "verify: drsim/cache_warm_from_snapshot is not allowed: "
        "verify calls must be read-only tools"
    ]
    assert execution.step(1).call is not None
    assert execution.step(1).call.risk_class is None
    assert execution.step(1).summary == errors[1][0]


def test_inferred_dependencies_shape_the_phases() -> None:
    execution, _ = _plan(executable_runbook(), inferred=[(2, [1]), (9, [1])])
    assert execution.step(2).phase == 2
    assert execution.step(2).depends_on == [1]
