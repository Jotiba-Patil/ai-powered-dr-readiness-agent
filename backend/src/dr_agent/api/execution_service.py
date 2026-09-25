"""The API's handle on the execution runtime: background advancing and shutdown.

Tool calls never run inside a request. After a decision, `kick()` starts
`engine.advance()` in a background task (the engine allows one per execution),
and the client polls `GET /executions/{id}`. A slow ticker also advances every
running execution, so approval timeouts fire without any request. On shutdown
the tasks are cancelled; a call cut off that way is left `RUNNING` in the
store and becomes `UNKNOWN` at the next start (restart recovery).
"""

from __future__ import annotations

import asyncio
import contextlib

from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.models import Execution, ExecutionState
from dr_agent.execution_runtime import ExecutionRuntime
from dr_agent.utils.errors import AppError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.api.execution")
DEFAULT_TICK_SECONDS = 15.0


class ExecutionService:
    def __init__(self, runtime: ExecutionRuntime, *, tick_seconds: float = DEFAULT_TICK_SECONDS):
        self.runtime = runtime
        self._tick_seconds = tick_seconds
        self._tasks: set[asyncio.Task[None]] = set()
        self._ticker: asyncio.Task[None] | None = None

    @property
    def engine(self) -> ExecutionEngine:
        return self.runtime.engine

    def kick(self, execution: Execution) -> Execution:
        """Runs whatever is ready in the background; returns the execution unchanged."""
        if execution.state is ExecutionState.RUNNING:
            task = asyncio.create_task(self._advance(execution.id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return execution

    async def settle(self) -> None:
        """Waits for the background work started so far (tests, graceful stops)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def start_ticker(self) -> None:
        self._ticker = asyncio.create_task(self._tick_forever())

    async def shutdown(self) -> None:
        tasks = [*self._tasks, *([self._ticker] if self._ticker else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _advance(self, execution_id: str) -> None:
        try:
            await self.engine.advance(execution_id)
        except AppError as exc:
            _log.warning("execution_advance_failed", execution_id=execution_id, code=exc.code)
        except Exception:  # a bug must not kill the event loop's other work; it is logged
            _log.exception("execution_advance_crashed", execution_id=execution_id)

    async def _tick_forever(self) -> None:
        while True:
            await asyncio.sleep(self._tick_seconds)
            with contextlib.suppress(AppError):
                for execution in await self.engine.list_all():
                    self.kick(execution)
