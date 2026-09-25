# 0001. Use the official MCP Python SDK behind a `ToolExecutor` protocol

- Status: Accepted (2026-09-24)
- Date: 2026-09-23
- Related: [design](../design/runbook-execution.md) sections 3 and 14, [ADR 0005](0005-bundled-mock-mcp-server.md)

## Context

Recovery steps will be carried out by calling tools on MCP servers. We need an MCP client that supports the stdio and streamable HTTP transports, exposes each tool's `inputSchema` and annotations, and can be tested without subprocesses or network. The project allows only open-source dependencies, and `core/`-style packages must not depend on concrete integrations.

## Decision

- Use the official MCP Python SDK (`mcp`, MIT license). Its `Client` connects to a stdio server (`StdioServerParameters`), a streamable HTTP URL, or an in-memory server object, which gives us one code path for production and tests.
- Hide it behind a small protocol in `tools/base.py`:
  - `list_tools() -> list[ToolSpec]` (server, name, description, input schema, annotations)
  - `call_tool(server, tool, arguments, timeout) -> ToolResult` (success flag, structured content or text, error)
- `tools/mcp_executor.py` is the only module that imports `mcp`. `execution/` depends on the protocol only, and `wiring.py` chooses between `McpToolExecutor` and `DryRunExecutor`.
- Servers are defined only in `MCP_SERVERS_FILE`, validated with Pydantic at startup.
- Connection setup and `list_tools` may be retried with backoff (`llm/retry.py` helper). `call_tool` is **never** retried automatically.
- Tool results are validated into `ToolResult` and truncated before storage; they are treated as untrusted data.

## Consequences

- Swapping the mock server for real servers is a configuration change.
- SDK version changes (the v2 SDK renamed `FastMCP` to `MCPServer` and replaced session helpers with `Client`) stay contained in `tools/mcp_executor.py` and `mock_mcp/`. We pin the version in `uv.lock` and use whichever major version is stable when Phase 10 starts.
- The SDK brings transitive dependencies (anyio, starlette, uvicorn, sse-starlette), all open source and mostly already present; `poe audit` covers them.
- The execution package can be tested with a fake `ToolExecutor`, without MCP at all.

## Alternatives considered

- **Hand-written JSON-RPC client over httpx.** No new dependency, but we would re-implement transports, initialization and capability negotiation, and track spec changes ourselves.
- **Letting the LLM call tools directly (agent framework with tool use).** Puts the model in the execution path and makes approvals harder to enforce; rejected on safety grounds.
- **Direct integrations (kubectl, psycopg, cloud SDKs) without MCP.** Every system would need its own adapter and policy surface; MCP gives one uniform, schema-described interface.
