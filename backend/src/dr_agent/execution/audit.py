"""Hash-chained audit events (design section 7).

`hash = SHA-256(prev_hash || canonical_json(event without hash))`, starting
from a genesis value derived from the execution id. `verify_chain()` recomputes
every link, so a changed, removed or reordered event is detected. Without an
external anchor the whole chain can still be rewritten: a documented PoC limit.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, JsonValue

from dr_agent.execution.canonical import canonical_json, sha256_hex
from dr_agent.models.base import CamelModel


class AuditEvent(CamelModel):
    seq: int = Field(ge=1)
    execution_id: str
    type: str = Field(min_length=1)
    actor: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    prev_hash: str
    hash: str
    created_at: datetime


class ChainVerification(CamelModel):
    valid: bool
    head: str
    events: int
    broken_at_seq: int | None = None


def genesis_hash(execution_id: str) -> str:
    return sha256_hex(f"dr-agent-audit-genesis:{execution_id}")


def event_hash(event: AuditEvent) -> str:
    body = event.model_dump(mode="json", by_alias=True, exclude={"hash"})
    return sha256_hex(event.prev_hash + canonical_json(body))


def build_event(
    *,
    execution_id: str,
    seq: int,
    prev_hash: str,
    event_type: str,
    actor: str,
    payload: dict[str, JsonValue],
    now: datetime,
) -> AuditEvent:
    event = AuditEvent(
        seq=seq,
        execution_id=execution_id,
        type=event_type,
        actor=actor,
        payload=payload,
        prev_hash=prev_hash,
        hash="",
        created_at=now,
    )
    event.hash = event_hash(event)
    return event


def verify_chain(execution_id: str, events: list[AuditEvent]) -> ChainVerification:
    prev = genesis_hash(execution_id)
    for expected_seq, event in enumerate(events, start=1):
        intact = (
            event.seq == expected_seq
            and event.execution_id == execution_id
            and event.prev_hash == prev
            and event.hash == event_hash(event)
        )
        if not intact:
            return ChainVerification(
                valid=False, head=prev, events=len(events), broken_at_seq=expected_seq
            )
        prev = event.hash
    return ChainVerification(valid=True, head=prev, events=len(events))
