---
paths:
  - "backend/**/*.py"
---

# Python backend rules

- Python 3.13 (3.13.2 pinned in `.python-version`), `mypy --strict`, ruff for lint and format. No `Any`, no `# type: ignore` without a reason comment.
- Pydantic v2 models for every boundary: files, API bodies, LLM output, config. Use `model_validate` and turn `ValidationError` into our own `ParseError` or `ValidationError` subclass of `AppError`.
- Error hierarchy lives in `utils/errors.py`: `AppError` -> `ParseError`, `ValidationError`, `AnalysisError`, `ConfigError`, plus request errors (`BadRequestError`, `NotFoundError`, `ConflictError`, ...) and execution errors (`ExecutionDisabledError`, `InvalidTransitionError`, `StaleCallError`, `PolicyViolationError`, `ToolError`). Each carries a stable `code` string; map new ones in `api/errors.py`.
- `core/`, `health/`, `execution/` and `tools/` import no FastAPI, Typer or Rich. Web and CLI layers call one shared `analyze_runbook()` service, and for executions the one `ExecutionEngine`.
- Execution: every step or execution state change goes through `execution/transitions.py` via a `Journal`, so it is saved together with its audit event. Tool calls go only through an injected `ToolExecutor`, never directly. Never add automatic retries of `call_tool`.
- The MCP SDK is imported only in `tools/mcp_executor.py`, `tools/mcp_convert.py` and `mock_mcp/` (tested). Everything a server returns is validated into `ToolSpec` / `ToolResult`. MCP servers come only from `MCP_SERVERS_FILE`; never log their env, headers or URLs with credentials.
- `execution_runtime.py` is the one place that builds the engine (API lifespan and CLI). API routes never run tool calls in the request except `rollback`; they call `ExecutionService.kick()`.
- MCP connections must be opened and closed in the same task (anyio); `McpToolExecutor` owns them in one background task, so keep it that way.
- History (ADR 0007): `storage/` owns the SQLite file and its numbered migrations (add a migration, never edit an applied one). `history/` is framework-free; `AnalysisStore` and `ExecutionStore` are injected. Saving an analysis never fails it (`History.save()` returns False), and the stored runbook text is never logged.
- Knowledge base (ADR 0009): `knowledge/` is framework-free; `KnowledgeSource` and `KnowledgeBase` are injected into `analyze_runbook()`. Facts come from live executions only, durations from audit event timestamps and state names only (never payload text). HISTORICAL gaps are rule-owned. Reading history never fails an analysis.
- Dependencies (health checker, LLM provider, clock, RNG) are passed in, never constructed inside core functions.
- Async all the way for I/O. Use `asyncio.gather(..., return_exceptions=True)` for parallel health checks and always apply timeouts.
- Logging via structlog only. Bind `request_id` and `correlation_id`. Never log runbook contents at info level or any secret.
- Config via pydantic-settings, validated at startup. No hardcoded URLs, models or ports.
- One responsibility per file, under 200 lines.
