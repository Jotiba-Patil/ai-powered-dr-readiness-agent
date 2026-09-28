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
- Scheduler tests use `backend/tests/unit/scheduling_support.py`: `FakeClock` (T0 = Sun 27 Sep 2026 05:00 UTC), `make_rig()` (SQLite store in `tmp_path`, `AnalyzeStub` that stores the golden report, `LogNotifier`, a static directory), `due_run()` and `started_run()` (held in the analysis with `gate`). SMTP is tested with a fake `smtplib.SMTP` plus one in-process `aiosmtpd` exchange on loopback only.
- Schedule API tests use `backend/tests/integration/schedule_api_support.py` (`schedule_client()` with the scheduler on and emails captured by a `LogNotifier`, `capture=False` for real SMTP to an in-process `aiosmtpd`; `settle()` waits for scheduled runs through the portal, no sleeps).
- Times: the UI tests run with `TZ=UTC` (`vite.config.ts`), the backend tests with `DISPLAY_TIMEZONE=UTC` (`backend/tests/conftest.py`); test other zones by passing a zone explicitly (`formatDateTime(iso, { timeZone })`, `display_time(value, ZoneInfo(...))`), and keep `test_timefmt.py` and `lib/formatDateTime.test.ts` on the same cases. Upload API tests use a copy of the sample folder in `tmp_path` (`allowed_dir()` in `test_api_uploads.py`), never the repository's `mock-data`.
- Execution API tests use `backend/tests/integration/exec_api_support.py` (`execution_client()` with the in-process mock server, `settle()` to wait for background advancing, no sleeps).
