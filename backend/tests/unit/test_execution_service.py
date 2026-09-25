"""ExecutionService: background advancing never crashes the app; the ticker kicks runs."""

import asyncio

from dr_agent.api.execution_service import ExecutionService
from dr_agent.execution.models import ExecutionState
from dr_agent.utils.errors import ToolError


class Run:
    def __init__(self, execution_id: str, state: ExecutionState) -> None:
        self.id, self.state = execution_id, state


class StubEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.advanced: list[str] = []
        self.runs = [Run("a", ExecutionState.RUNNING), Run("b", ExecutionState.PAUSED)]

    async def advance(self, execution_id: str) -> None:
        self.advanced.append(execution_id)
        if self.error:
            raise self.error

    async def list_all(self) -> list[Run]:
        return self.runs


class StubRuntime:
    def __init__(self, engine: StubEngine) -> None:
        self.engine = engine


def _service(engine: StubEngine, tick: float = 3600) -> ExecutionService:
    return ExecutionService(StubRuntime(engine), tick_seconds=tick)  # type: ignore[arg-type]  # stub


async def test_only_running_executions_are_advanced() -> None:
    engine = StubEngine()
    service = _service(engine)
    for run in engine.runs:
        service.kick(run)  # type: ignore[arg-type]  # stub
    await service.settle()
    assert engine.advanced == ["a"]


async def test_errors_and_crashes_in_the_background_are_contained() -> None:
    for error in (ToolError("down"), RuntimeError("bug")):
        engine = StubEngine(error)
        service = _service(engine)
        service.kick(engine.runs[0])  # type: ignore[arg-type]  # stub
        await service.settle()
        assert engine.advanced == ["a"]


async def test_ticker_kicks_running_executions_until_shutdown() -> None:
    engine = StubEngine()
    service = _service(engine, tick=0)
    service.start_ticker()
    while len(engine.advanced) < 2:
        await asyncio.sleep(0)
    await service.shutdown()
    assert set(engine.advanced) == {"a"}
