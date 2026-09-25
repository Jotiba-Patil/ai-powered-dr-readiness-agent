"""Execution API step decisions: failure + rollback, retry, reject/manual/skip, edits, abort."""

from pathlib import Path

from exec_api_support import (
    APPROVERS,
    BASE,
    OPERATOR,
    act,
    approve_all,
    call_hash,
    create,
    execution_client,
    step,
)

from dr_agent.mock_mcp.state import Scenario, ToolFault


def test_failure_then_two_person_rollback(tmp_path: Path) -> None:
    faults = {"smoke_run": ToolFault(fail_on_calls=[1], message="checkout 500s")}
    with execution_client(tmp_path, Scenario(faults=faults)) as (client, env):
        execution = approve_all(client, create(client))
        act(client, execution["id"], "start")()
        verify = {"actor": "Ann", "succeeded": True}
        execution = act(client, execution["id"], "steps/1/verify", verify)()
        assert step(execution, 5)["state"] == "FAILED"
        assert execution["state"] == "PAUSED"
        assert execution["pauseReason"] == "step 5 failed"

        rollback_hash = call_hash(execution, 5, "rollback")
        for name in APPROVERS:
            response = client.post(
                f"{BASE}/{execution['id']}/steps/5/approve",
                json={"approver": name, "callHash": rollback_hash, "kind": "rollback"},
            )
            assert response.status_code == 200, response.text
        execution = act(client, execution["id"], "steps/5/rollback")()
        assert step(execution, 5)["state"] == "ROLLED_BACK"
        assert env.state.dns["estimate-service"] == "primary"
        closed = client.post(
            f"{BASE}/{execution['id']}/close", json={"actor": OPERATOR, "reason": "abandoned"}
        )
        assert closed.json()["state"] == "FAILED"


def test_retry_after_a_failed_restart(tmp_path: Path) -> None:
    faults = {"k8s_rollout_restart": ToolFault(fail_on_calls=[1], message="ImagePullBackOff")}
    with execution_client(tmp_path, Scenario(faults=faults)) as (client, _):
        execution = approve_all(client, create(client))
        execution = act(client, execution["id"], "start")()
        assert step(execution, 2)["state"] == "FAILED"
        execution = act(client, execution["id"], "steps/2/retry")()
        assert (step(execution, 2)["state"], step(execution, 2)["attempt"]) == (
            "AWAITING_APPROVAL",
            2,
        )
        act(
            client,
            execution["id"],
            "steps/2/approve",
            {"approver": "Ann", "callHash": call_hash(execution, 2)},
        )
        execution = act(client, execution["id"], "resume")()
        assert step(execution, 2)["state"] == "SUCCEEDED"


def test_reject_manual_skip_and_edit(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, _):
        execution = create(client)
        eid = execution["id"]
        missing_reason = client.post(f"{BASE}/{eid}/steps/1/reject", json={"actor": "Ann"})
        assert missing_reason.status_code == 422
        execution = act(client, eid, "steps/1/reject", {"actor": "Ann", "reason": "wrong region"})()
        assert step(execution, 1)["state"] == "REJECTED"
        execution = act(client, eid, "steps/1/manual", {"actor": "Ann", "reason": "by hand"})()
        assert step(execution, 1)["state"] == "AWAITING_MANUAL"
        execution = act(client, eid, "steps/1/mark-done", {"actor": "Ann"})()
        assert step(execution, 1)["state"] == "MANUAL_DONE"
        execution = act(client, eid, "steps/4/skip", {"actor": "Ann", "reason": "cache is warm"})()
        assert step(execution, 4)["state"] == "SKIPPED"

        edited = client.put(
            f"{BASE}/{eid}/steps/2/call",
            json={
                "editor": "Ann",
                "call": {
                    "server": "drsim",
                    "tool": "k8s_rollout_restart",
                    "arguments": {"deployment": "estimate-service", "region": "primary"},
                },
            },
        )
        assert edited.status_code == 200, edited.text
        call = step(edited.json(), 2)["call"]
        assert (call["source"], call["arguments"]["region"]) == ("edited", "primary")
        off_list = client.put(
            f"{BASE}/{eid}/steps/2/call",
            json={"editor": "Ann", "call": {"server": "drsim", "tool": "rm_rf", "arguments": {}}},
        )
        assert (off_list.status_code, off_list.json()["code"]) == (422, "POLICY_VIOLATION")
        no_outcome = client.post(f"{BASE}/{eid}/steps/2/verify", json={"actor": "Ann"})
        assert no_outcome.status_code == 422


def test_abort_is_always_available(tmp_path: Path) -> None:
    with execution_client(tmp_path) as (client, env):
        execution = approve_all(client, create(client))
        act(client, execution["id"], "start")()
        paused = act(client, execution["id"], "pause", {"actor": OPERATOR, "reason": "hold"})()
        assert paused["state"] == "PAUSED"
        aborted = act(
            client, execution["id"], "abort", {"actor": OPERATOR, "reason": "drill over"}
        )()
        assert aborted["state"] == "ABORTED"
        again = client.post(
            f"{BASE}/{execution['id']}/abort", json={"actor": OPERATOR, "reason": "x"}
        )
        assert again.status_code == 409
        assert env.call_counts["db_promote_replica"] == 0
