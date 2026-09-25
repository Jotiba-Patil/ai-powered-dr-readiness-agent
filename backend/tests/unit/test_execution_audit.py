"""Hash-chained audit events: build, verify, and detect tampering."""

from datetime import UTC, datetime

from dr_agent.execution.audit import AuditEvent, build_event, genesis_hash, verify_chain

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _chain(execution_id: str = "e1", length: int = 3) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    prev = genesis_hash(execution_id)
    for seq in range(1, length + 1):
        event = build_event(
            execution_id=execution_id,
            seq=seq,
            prev_hash=prev,
            event_type="step_state",
            actor="system",
            payload={"step": seq, "to": "RUNNING"},
            now=NOW,
        )
        events.append(event)
        prev = event.hash
    return events


def test_intact_chain_verifies() -> None:
    events = _chain()
    result = verify_chain("e1", events)
    assert result.valid
    assert result.head == events[-1].hash
    assert result.events == 3
    assert result.broken_at_seq is None


def test_empty_chain_is_valid_with_the_genesis_head() -> None:
    assert verify_chain("e1", []).head == genesis_hash("e1")


def test_genesis_differs_per_execution() -> None:
    assert genesis_hash("e1") != genesis_hash("e2")


def test_changed_payload_is_detected() -> None:
    events = _chain()
    events[1].payload["to"] = "SUCCEEDED"
    assert verify_chain("e1", events).broken_at_seq == 2


def test_removed_event_is_detected() -> None:
    events = _chain()
    del events[1]
    result = verify_chain("e1", events)
    assert not result.valid
    assert result.broken_at_seq == 2


def test_reordered_events_are_detected() -> None:
    events = _chain()
    events[0], events[1] = events[1], events[0]
    assert verify_chain("e1", events).broken_at_seq == 1


def test_rehashed_event_without_relinking_the_chain_is_detected() -> None:
    events = _chain()
    events[0] = build_event(
        execution_id="e1",
        seq=1,
        prev_hash=events[0].prev_hash,
        event_type=events[0].type,
        actor="mallory",
        payload=events[0].payload,
        now=NOW,
    )
    assert verify_chain("e1", events).broken_at_seq == 2


def test_events_of_another_execution_are_rejected() -> None:
    assert verify_chain("e2", _chain("e1")).broken_at_seq == 1
