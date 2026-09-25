"""Composition root for runbook execution, shared by the API lifespan and `dr-agent execute`.

`open_execution_runtime()` loads the policy and `MCP_SERVERS_FILE`, opens the
SQLite store, runs restart recovery (in-flight calls become `UNKNOWN`), connects
to the MCP servers and builds the engine. Dry runs use a `DryRunExecutor` built
from the servers' own tool catalog, so they are checked against real schemas
but never call a tool. Must be entered and left in the same task.
"""

from __future__ import annotations

import os
import random
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dr_agent.config import Settings
from dr_agent.execution.engine import ExecutionEngine
from dr_agent.execution.policy_file import ExecutionPolicy, load_policy
from dr_agent.execution.proposer import ToolProposer
from dr_agent.execution.recovery import recover_interrupted
from dr_agent.execution.session import ExecutionLimits
from dr_agent.execution.sqlite_store import SqliteExecutionStore
from dr_agent.llm.base import LLMProvider
from dr_agent.tools.base import ToolSpec
from dr_agent.tools.dry_run import DryRunExecutor
from dr_agent.tools.mcp_convert import ClientFactory, client_factory
from dr_agent.tools.mcp_executor import McpToolExecutor
from dr_agent.tools.servers_config import load_servers
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.execution")


@dataclass(frozen=True)
class ExecutionRuntime:
    engine: ExecutionEngine
    policy: ExecutionPolicy
    limits: ExecutionLimits
    tools: list[ToolSpec]
    recovered: list[str]


@asynccontextmanager
async def open_execution_runtime(
    settings: Settings,
    llm: LLMProvider,
    *,
    rng: random.Random,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    factories: Mapping[str, ClientFactory] | None = None,
) -> AsyncIterator[ExecutionRuntime]:
    """`factories` replaces `MCP_SERVERS_FILE` (tests pass in-process servers)."""
    policy = load_policy(Path(settings.execution_policy_file))
    if factories is None:
        servers = load_servers(Path(settings.mcp_servers_file), os.environ)
        factories = {key: client_factory(config) for key, config in servers.items()}
    store = await SqliteExecutionStore.open(settings.database_path)
    recovered = await recover_interrupted(store, clock)
    if recovered:
        _log.warning("executions_recovered", count=len(recovered))
    limits = ExecutionLimits.from_settings(settings)
    async with McpToolExecutor(factories, rng=rng) as live:
        tools = await live.list_tools()
        use_ai = settings.execution_ai_proposals and settings.llm_provider != "none"
        engine = ExecutionEngine(
            store=store,
            executor=live,
            dry_run_executor=DryRunExecutor(tools),
            policy=policy,
            limits=limits,
            clock=clock,
            proposer=ToolProposer(llm) if use_ai else None,
        )
        _log.info("execution_ready", servers=len(factories), tools=len(tools))
        yield ExecutionRuntime(engine, policy, limits, tools, recovered)
