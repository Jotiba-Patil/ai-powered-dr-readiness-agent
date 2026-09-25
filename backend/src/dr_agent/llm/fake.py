"""FakeProvider: a deterministic, in-memory `LLMProvider` for tests and demos.

Replays a fixed sequence of responses (or raises a fixed transport error) so
tests can exercise the decode-retry, validation-retry and graceful-degradation
paths without ever touching a network or a real model.
"""

from __future__ import annotations

from dr_agent.utils.errors import AnalysisError


class FakeProvider:
    def __init__(
        self, responses: list[str], *, transport_error: AnalysisError | None = None
    ) -> None:
        self._responses = list(responses)
        self._transport_error = transport_error
        self.calls: list[tuple[str, str]] = []

    async def generate(
        self, *, system_prompt: str, user_prompt: str, schema: dict[str, object]
    ) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self._transport_error is not None:
            raise self._transport_error
        if not self._responses:
            raise AssertionError("FakeProvider ran out of scripted responses")
        return self._responses.pop(0)
