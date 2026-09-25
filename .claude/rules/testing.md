---
paths:
  - "backend/tests/**"
  - "frontend/**/*.test.*"
---

# Testing rules

- Write tests in the same change as the code. Coverage gate is 80% (`--cov-fail-under=80`).
- Never call a real LLM or real network in tests. Use the fake `LLMProvider` and `MockHealthChecker` with a seeded RNG.
- Parser tests are table-driven over `mock-data/runbooks/` and `backend/tests/fixtures/` (empty file, no headers, malformed, mixed time units, tables, bullets).
- LLM analyzer tests must cover: valid output, malformed JSON, schema-invalid then corrected on retry, transport failure with backoff, graceful degradation.
- Formatter tests use snapshots. Update snapshots only when the change is intended and say so.
- API tests use FastAPI TestClient or httpx ASGI transport. CLI tests use `typer.testing.CliRunner`, plus one subprocess test for exit codes.
- Tests are deterministic: no sleeps, no wall-clock, no random without a seed.
- Execution tests use the helpers in `backend/tests/unit/exec_support.py`: the `drsim` catalog and policy, an injected `Clock`, `make_engine()` with a SQLite file in `tmp_path`, and `FakeExecutor` (scripted outcomes, `gate` to hold a call in flight) or `DryRunExecutor`. Transition tables are tested exhaustively against an independent copy of the design.
- MCP tests use the bundled mock server through the SDK's in-memory client (`McpToolExecutor({"drsim": lambda: Client(build_server(env))}, ...)`); hold a call in flight with `DrEnvironment.before_call`, inject failures with `Scenario(faults=...)`. Keep `exec_support.DRSIM` in sync with the mock (checked by `test_mock_mcp_server.py`). Only stdio subprocess tests (mock server, `dr-agent execute`); no network.
- History is on by default: `backend/tests/conftest.py` points `DB_PATH` at `tmp_path` for every test, so nothing writes to the repository. History tests use `backend/tests/unit/history_support.py` (`make_record()` from the golden report, `store_execution()` for linked executions).
- Knowledge tests use `backend/tests/unit/knowledge_support.py` (`finished_run()`: a live run with a hand-made audit trail and step timings) and the fixture `backend/tests/fixtures/history/estimate-service.json` (also behind the second golden report). The Phase 14 exit test `integration/test_knowledge_mcp.py` runs real live executions against the mock MCP server.
- Execution API tests use `backend/tests/integration/exec_api_support.py` (`execution_client()` with the in-process mock server, `settle()` to wait for background advancing, no sleeps).
