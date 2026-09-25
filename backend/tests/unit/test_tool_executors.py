"""Tool result validation plus the dry-run and fake executors."""

import pytest
from exec_support import drsim_catalog

from dr_agent.tools.base import MAX_RESULT_CHARS, ToolResult, ToolSpec
from dr_agent.tools.dry_run import DryRunExecutor
from dr_agent.tools.fake import FakeExecutor
from dr_agent.utils.errors import ToolError


def test_long_content_is_truncated() -> None:
    result = ToolResult(ok=True, content="x" * (MAX_RESULT_CHARS + 50))
    assert len(result.content) == MAX_RESULT_CHARS
    assert result.content.endswith("[truncated]")


def test_large_structured_content_is_replaced() -> None:
    result = ToolResult(ok=True, structured={"blob": "y" * MAX_RESULT_CHARS})
    assert result.structured == {"truncated": True}
    assert ToolResult(ok=True, structured={"a": 1}).structured == {"a": 1}


def test_tool_spec_defaults_to_an_object_schema() -> None:
    assert ToolSpec(server="s", name="t").input_schema == {"type": "object"}


async def test_dry_run_simulates_success_and_never_calls_out() -> None:
    executor = DryRunExecutor(drsim_catalog())
    assert len(await executor.list_tools()) == 9
    result = await executor.call_tool(
        "drsim", "cache_ping", {"cache": "pricing-cache"}, timeout_seconds=1
    )
    assert result.ok
    assert result.simulated
    assert result.content == 'dry run: would call drsim/cache_ping {"cache": "pricing-cache"}'
    assert executor.calls == [("drsim", "cache_ping", {"cache": "pricing-cache"})]


async def test_dry_run_refuses_unknown_tools() -> None:
    with pytest.raises(ToolError, match="unknown tool"):
        await DryRunExecutor(drsim_catalog()).call_tool("drsim", "rm", {}, timeout_seconds=1)


async def test_fake_executor_replays_scripted_outcomes() -> None:
    executor = FakeExecutor(drsim_catalog())
    executor.script("drsim", "smoke_run", ToolResult(ok=False, content="red"), ToolError("down"))
    first = await executor.call_tool("drsim", "smoke_run", {}, timeout_seconds=1)
    assert not first.ok
    with pytest.raises(ToolError):
        await executor.call_tool("drsim", "smoke_run", {}, timeout_seconds=1)
    assert (await executor.call_tool("drsim", "smoke_run", {}, timeout_seconds=1)).ok
    assert len(executor.calls) == 3
    assert executor.started.is_set()
