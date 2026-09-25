"""`McpToolExecutor`: the `ToolExecutor` that talks to MCP servers (ADR 0001).

Used as an async context manager: entering connects to every configured
server (stdio, streamable HTTP, or an in-process server in tests) and lists its
tools; leaving closes the connections. Connecting and listing are retried with
backoff; `call_tool` is never retried, because recovery actions are usually not
idempotent (ADR 0006). Errors never carry server URLs, headers or environment.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from types import TracebackType

from mcp import Client
from pydantic import JsonValue

from dr_agent.llm.retry import DEFAULT_MAX_RETRIES, backoff_seconds
from dr_agent.tools.base import ToolResult, ToolSpec
from dr_agent.tools.mcp_convert import ClientFactory, client_factory, to_tool_result, to_tool_spec
from dr_agent.tools.servers_config import HttpServerConfig, StdioServerConfig
from dr_agent.utils.errors import ToolError
from dr_agent.utils.logging import get_logger

_log = get_logger("dr_agent.tools.mcp")


class McpToolExecutor:
    def __init__(
        self,
        factories: Mapping[str, ClientFactory],
        *,
        rng: random.Random,
        attempts: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._factories = dict(factories)
        self._rng, self._attempts, self._sleep = rng, attempts, sleep
        self._clients: dict[str, Client] = {}
        self._tools: dict[str, list[ToolSpec]] = {}
        self._stack = AsyncExitStack()
        self._stop = asyncio.Event()
        self._owner: asyncio.Task[None] | None = None

    @classmethod
    def from_configs(
        cls, configs: Mapping[str, StdioServerConfig | HttpServerConfig], *, rng: random.Random
    ) -> McpToolExecutor:
        return cls({key: client_factory(config) for key, config in configs.items()}, rng=rng)

    async def __aenter__(self) -> McpToolExecutor:
        """Connects every server in a dedicated owner task and waits until all are listed."""
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._stop = asyncio.Event()
        owner = self._owner = asyncio.create_task(self._own_connections(ready))
        try:
            await ready
        except BaseException:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._owner is None:
            return
        (outcome,) = await asyncio.gather(self._owner, return_exceptions=True)
        if isinstance(outcome, Exception):
            _log.warning("mcp_close_failed", error_type=type(outcome).__name__)

    async def _own_connections(self, ready: asyncio.Future[None]) -> None:
        """anyio needs a connection closed in the task that opened it, so one task owns them all."""
        try:
            async with AsyncExitStack() as stack:
                self._stack = stack
                for server in self._factories:
                    self._clients[server] = await self._retry(server, "connect", self._connect)
                    await self._list(server)
                ready.set_result(None)
                await self._stop.wait()
        except BaseException as exc:
            if ready.done():
                raise
            ready.set_exception(exc)
        finally:
            self._clients.clear()

    async def list_tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for server in self._clients:
            specs.extend(self._tools.get(server) or await self._list(server))
        return specs

    async def refresh(self) -> list[ToolSpec]:
        """Lists every server's tools again (for example after a server upgrade)."""
        self._tools.clear()
        return await self.list_tools()

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, JsonValue], *, timeout_seconds: float
    ) -> ToolResult:
        client = self._clients.get(server)
        if client is None:
            raise ToolError(f"MCP server '{server}' is not connected", details={"server": server})
        try:
            result = await client.call_tool(tool, arguments, read_timeout_seconds=timeout_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # any transport or protocol failure; the call may have run
            _log.warning("mcp_call_failed", server=server, tool=tool, error_type=type(exc).__name__)
            raise ToolError(
                f"{server}/{tool} did not complete ({type(exc).__name__}); its outcome is unknown",
                details={"server": server, "tool": tool},
            ) from exc
        return to_tool_result(result)

    async def _connect(self, server: str) -> Client:
        client = self._factories[server]()
        return await self._stack.enter_async_context(client)

    async def _list(self, server: str) -> list[ToolSpec]:
        async def fetch(key: str) -> list[ToolSpec]:
            client = self._clients[key]
            specs: list[ToolSpec] = []
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                specs.extend(to_tool_spec(key, tool) for tool in page.tools)
                cursor = page.next_cursor
                if cursor is None:
                    return specs

        self._tools[server] = await self._retry(server, "list tools", fetch)
        return self._tools[server]

    async def _retry[T](
        self, server: str, action: str, operation: Callable[[str], Awaitable[T]]
    ) -> T:
        for attempt in range(self._attempts):
            try:
                return await operation(server)
            except ToolError:
                raise
            except Exception as exc:  # connection and protocol errors of any transport
                _log.warning(
                    "mcp_retry",
                    server=server,
                    action=action,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
                if attempt + 1 == self._attempts:
                    raise ToolError(
                        f"cannot {action} on MCP server '{server}' ({type(exc).__name__})",
                        details={"server": server, "attempts": self._attempts},
                    ) from exc
                await self._sleep(backoff_seconds(self._rng, attempt))
        raise AssertionError("unreachable")  # pragma: no cover - the loop always returns or raises
