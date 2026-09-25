import pytest

from dr_agent.llm.fake import FakeProvider
from dr_agent.utils.errors import AnalysisError


async def test_returns_scripted_responses_in_order() -> None:
    provider = FakeProvider(["first", "second"])
    first = await provider.generate(system_prompt="sys", user_prompt="a", schema={})
    second = await provider.generate(system_prompt="sys", user_prompt="b", schema={})
    assert (first, second) == ("first", "second")


async def test_records_every_call() -> None:
    provider = FakeProvider(["ok"])
    await provider.generate(system_prompt="sys", user_prompt="user text", schema={})
    assert provider.calls == [("sys", "user text")]


async def test_raises_configured_transport_error() -> None:
    error = AnalysisError("boom")
    provider = FakeProvider([], transport_error=error)
    with pytest.raises(AnalysisError):
        await provider.generate(system_prompt="sys", user_prompt="a", schema={})


async def test_running_out_of_responses_raises() -> None:
    provider = FakeProvider(["only one"])
    await provider.generate(system_prompt="sys", user_prompt="a", schema={})
    with pytest.raises(AssertionError):
        await provider.generate(system_prompt="sys", user_prompt="a", schema={})
