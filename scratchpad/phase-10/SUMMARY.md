# Phase 10 summary: MCP integration

Date: 2026-09-24. Status: done. Exit criteria met (evidence below).

## Goal
Connect the Phase 9 execution core to real MCP: an MCP client behind `ToolExecutor`, a bundled mock MCP server that simulates a DR environment with fault injection, default server and policy files, and AI tool-call proposals for unannotated steps (design sections 3, 4.3 and 10; ADRs 0001, 0002 and 0005).

## Before starting: re-verification of Phases 0-9
- `ruff check`, `ruff format --check`, `mypy --strict` (94 files) clean; 830 backend tests, 99.09% coverage; UI eslint/tsc/prettier clean, 43 vitest tests; no file over 200 lines.

## Produced
MCP client (`backend/src/dr_agent/tools/`)
- `servers_config.py`: `MCP_SERVERS_FILE` with `stdio` (`command`, `args`, `env`, `cwd`) and `http` (`url`, `headers`) entries, `${VAR}` resolution from the environment (unset variables are named, never guessed), env and header values held as `SecretStr`, and validation errors that never echo input.
- `mcp_executor.py`: `McpToolExecutor`, an async context manager. One owner task opens every connection, lists the tools and closes the connections on exit. Connecting and listing are retried with backoff (shared `llm/retry.py`); `call_tool` is never retried, and a failed call raises `ToolError` saying its outcome is unknown.
- `mcp_convert.py`: builds SDK `Client`s from config (stdio, plain URL, or streamable HTTP with headers), and turns tool listings and results into `ToolSpec` (descriptions capped at 1,000 characters) and `ToolResult` (16 KB).

Mock MCP server (`backend/src/dr_agent/mock_mcp/`)
- `state.py`: environment state and scenario models. The default is the estimate-service regional outage: primary down, standby scaled down, replica in recovery, cache cold, DNS on primary.
- `environment.py`: `DrEnvironment` with the effects of the nine tools, faults per tool (`failOnCalls`, `failAlways`, `latencyMs`), call counts, and a `before_call` hook for tests.
- `server.py`: the `drsim` `MCPServer` with the nine tools from ADR 0005 and their MCP annotations; anticipated failures become MCP tool errors with a readable message.
- `__main__.py`: `python -m dr_agent.mock_mcp [--transport stdio|http] [--host] [--port] [--scenario FILE]`, with `MOCK_MCP_SCENARIO` as the fallback.
- `mock-data/scenarios/`: `smoke-fails-once.json`, `slow-promotion.json`.

Defaults (repo root)
- `mcp-servers.json`: the mock server over stdio (`python -m dr_agent.mock_mcp`).
- `execution-policy.json`: exactly the nine tools, risk classes matching the server's hints, and constraints on `region` and `snapshot`.

AI proposals
- `llm/proposal_schema.py` (`ToolProposal`: one call, or `manual` with a reason), `llm/prompts/execution.py` (`execution-proposal/1`, step and tools as escaped JSON inside `<step>` / `<tools>`), and `llm/parse.py` generalized to `get_validated()` for any schema (`get_llm_analysis()` unchanged).
- `execution/proposer.py`: `ToolProposer` and `propose_missing()`. The planner puts a valid proposal in `PROPOSED` (source `ai_proposed`, `StepRun.proposal` holds the rationale and confidence, audit event `proposal`); an unusable one makes the step `AWAITING_MANUAL` with the reason. `ExecutionEngine` takes an optional `proposer`.

Sample runbook: `estimate-service-executable.md` verify calls now state their expectation (`expect_ready: true`, `expect_in_recovery: false`).

Dependency: `mcp` 2.2.0 (MIT). New transitive packages, all open source: `mcp-types` (MIT), `sse-starlette` (BSD-3), `pyjwt` (MIT), `cryptography` (Apache-2.0/BSD), `cffi` (MIT-0), `pycparser` (BSD-3), `opentelemetry-api` (Apache-2.0), `pywin32` (PSF, Windows only).

## Documentation updated
- `README.md`: status, What it does, Stack, the architecture sketch (proposer, MCP client, mock server), layout (`mock_mcp/`, the new `tools/` files, default config files, `mock-data/scenarios/`, `scratchpad/phase-10`), the Runbook execution section (AI proposals, mock MCP server and scenarios, MCP client), configuration (`MOCK_MCP_SCENARIO`), Swapping in real integrations, roadmap, security notes.
- `docs/IMPLEMENTATION_PLAN.md` (Phase 10), `docs/design/runbook-execution.md` (section 17, Phase 10 notes).
- `CLAUDE.md` (stack, layout, mock server command), `.claude/rules/python-backend.md`, `llm-and-security.md`, `testing.md`, `.claude/skills/dr-runbook-parser`, `.env.example`.

## Decisions and deviations
- P10-1 **SDK version.** `mcp` 2.2.0, the current major version: one `Client` for stdio, URL and in-process servers, and `MCPServer` for the mock (ADR 0001 anticipated both).
- P10-2 **Two SDK modules on the client side.** `tools/mcp_convert.py` sits next to `tools/mcp_executor.py` and also imports the SDK, so each file stays under 200 lines. ADR 0001 named only `mcp_executor.py`. `test_package.py` enforces that no other module (outside `mock_mcp/`) imports `mcp`.
- P10-3 **Connections live in one owner task.** anyio requires a connection to be closed in the task that opened it. The first version broke when entered and exited from different tasks (found by a pytest-asyncio fixture), and an API lifespan could hit the same problem. The owner task opens every connection, waits for a stop signal and closes them; calls can come from any task.
- P10-4 **Persistent connections, not one per call.** Tool calls reuse the connection opened on entry. With stdio, one connection per call would also restart the mock server and lose its state. If a connection breaks, calls fail with `ToolError` and the executor must be re-entered; there is no reconnect in the middle of a run (Phase 11 wiring decides when to rebuild it).
- P10-5 **Verify calls state their expectation.** A successful MCP call only means the tool ran, so the mock's read tools take optional `expect_ready` / `expect_in_recovery` and fail when the expectation is not met. `cache_ping` fails while the cache is cold, and `smoke_run` fails listing the failed checks. The engine's rule "a verify call passes when the tool succeeds" is unchanged.
- P10-6 **Tool error messages carry the SDK prefix** ("Error executing tool smoke_run: ..."). They are kept as the server sends them, truncated to 500 characters on the step.
- P10-7 **Proposals are requested once, when the execution is created**, one model call per unannotated step, in order. With `LLM_PROVIDER=none`, or when the model fails, those steps are manual with the reason recorded. A proposal is re-checked against policy like any call. Accepting it (`EditCall` with no new call) keeps the source `ai_proposed`; editing it makes it `edited`.
- P10-8 **Two sample scenarios** in `mock-data/scenarios/` for drills. They are not served by the samples endpoint, which lists only runbooks and inventories.
- P10-9 **Deferred to Phase 11:** building the executor, proposer and engine from settings in `wiring.py`, the API lifespan (enter the executor, run `recover_interrupted()`), the Docker `mock-mcp` service (streamable HTTP on an internal network), and copying the default config files into the image.

## Evidence
- Exit test `backend/tests/integration/test_execution_mcp.py`. The real `McpToolExecutor` talks to the mock server through the SDK's in-memory client, with the repo's `execution-policy.json` and a SQLite store in `tmp_path`:
  - full failover: `COMPLETED`, 9 tool calls, DNS on standby, replica promoted, cache warm, smoke checks all true, audit chain valid;
  - injected smoke-test failure: step 5 `FAILED` and the execution paused; the rollback, approved by two people (destructive), leaves step 5 `ROLLED_BACK` with DNS back on primary; then the execution is closed;
  - abort mid-call (`db_promote_replica` held in the server): step 3 `UNKNOWN`, the promotion did happen, and no later tool was called;
  - restart recovery with the same held call: step 3 `UNKNOWN`, execution `PAUSED`; a person reports the outcome, the run is resumed and completes, and the promotion was sent exactly once.
- Transports: `test_mcp_stdio.py` spawns `python -m dr_agent.mock_mcp` over stdio (state kept for the session). A manual check of streamable HTTP (`--transport http --port 8765`, listed 9 tools, promote then "already the primary") also passed; it is not an automated test, because tests do not use the network.
- `test_default_execution_config.py`: the policy allow-lists exactly the server's tools, the hints never need to raise a risk class, and all 11 calls of the executable sample pass the default policy.
- Gate: `ruff check` and `ruff format --check` clean (182 files), `mypy --strict` clean (105 source files), 883 backend tests at 98.94% coverage, 43 UI tests, eslint/tsc/prettier clean, every file under 200 lines. `pip-audit`: no known vulnerabilities; `npm audit`: 0.

## Environment note
The uv launcher problem from Phase 9 is still present (`uv trampoline failed to canonicalize script path`). The gate was run through `python -m`.

## Next (Phase 11, not started)
`api/routes_execution.py` and schemas, `dr-agent execute`, the UI Execute view, wiring and lifespan (executor, proposer, recovery), Docker `mock-mcp` service and `executions-data` volume, docs.
