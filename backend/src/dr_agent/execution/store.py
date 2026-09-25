"""`ExecutionStore` protocol: durable executions plus their append-only audit log.

`save()` writes the execution and its new audit events in one transaction and
refuses events that do not continue the stored chain, so two writers can never
interleave events for one execution.
"""

from __future__ import annotations

from typing import Protocol

from dr_agent.execution.audit import AuditEvent
from dr_agent.execution.models import Execution


class ExecutionStore(Protocol):
    async def create(self, execution: Execution, events: list[AuditEvent]) -> None: ...

    async def save(self, execution: Execution, events: list[AuditEvent]) -> None: ...

    async def get(self, execution_id: str) -> Execution:
        """Raises `NotFoundError` for an unknown id."""
        ...

    async def list_all(self) -> list[Execution]:
        """Newest first."""
        ...

    async def audit(self, execution_id: str) -> list[AuditEvent]:
        """In sequence order. Raises `NotFoundError` for an unknown id."""
        ...
