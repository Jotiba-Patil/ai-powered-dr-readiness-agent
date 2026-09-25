"""Performance timing with an injectable clock (deterministic in tests)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from structlog.typing import FilteringBoundLogger

Clock = Callable[[], float]


class Stopwatch:
    """Measures elapsed milliseconds between construction and `stop()`."""

    def __init__(self, clock: Clock = time.perf_counter) -> None:
        self._clock = clock
        self._start = clock()
        self._end: float | None = None

    def stop(self) -> float:
        if self._end is None:
            self._end = self._clock()
        return self.elapsed_ms

    @property
    def elapsed_ms(self) -> float:
        end = self._clock() if self._end is None else self._end
        return (end - self._start) * 1000.0


@contextmanager
def timed(
    logger: FilteringBoundLogger | None = None,
    event: str = "timing",
    clock: Clock = time.perf_counter,
) -> Iterator[Stopwatch]:
    """Time a block. Logs `<event>` with `duration_ms` at debug level when a logger is given."""
    watch = Stopwatch(clock)
    try:
        yield watch
    finally:
        watch.stop()
        if logger is not None:
            logger.debug(event, duration_ms=round(watch.elapsed_ms, 2))
