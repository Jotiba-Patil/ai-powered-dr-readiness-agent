# Phase 9 summary: execution core

Date: 2026-09-24. Status: done. Exit criteria met (evidence below).

## Goal
Build the framework-free core for human-authorized runbook execution (design `docs/design/runbook-execution.md`, ADRs 0001-0006): runbook tool annotations, state machines, policy, approvals, audit chain, durable store, and an engine that runs a plan against injected executors. No API, CLI, UI or MCP yet (Phases 10-11).

## Before starting: re-verification of Phases 0-8
- Plan, all phase summaries and the Phase 8 design/ADRs re-read.
- `ruff check`, `ruff format --check`, `mypy --strict` (67 files) clean; 413 backend tests, 98.85% coverage; UI eslint/tsc/prettier clean, 43 vitest tests (99.48% lines); no file over 200 lines.
- Phase 8 approved by the project owner (this session). The design status and ADRs 0001-0006 were moved from Proposed to Accepted, and the plan and Phase 8 summary were updated to match.

## Produced
Parser and models
- `models/runbook.py`: `PlannedToolCall` (server, tool, JSON arguments); `Step.tool_call`, `verify_call`, `rollback_call` (default `None`).
- `core/annotations.py`: `<server>/<tool> {JSON}` parsing (arguments optional, default `{}`), list-item labels `Tool:` / `Verify-Tool:` / `Rollback-Tool:` (also with a space), table columns `Tool` / `Verify Tool` / `Rollback Tool`. Bad or duplicate annotations give a parser warning and are ignored.
- `core/step_extractor.py`, `core/step_table_extractor.py`: read the annotations; annotation items are never taken as validation commands.
- `core/dependency_graph.py`: `merge_depends_on()`, moved out of `core/analyzer.py` and shared with the planner.
- `mock-data/runbooks/estimate-service-executable.md`: every step annotated (5 main, 4 verify, 2 rollback calls). Existing samples untouched.

Execution (`backend/src/dr_agent/execution/`, all under 200 lines, no framework imports)
- `models.py`, `canonical.py` (canonical JSON, call hash), `transitions.py` (step and execution tables).
- `policy_file.py` (policy document, shell-like tool names refused), `policy.py` (allow-list, offered-by-server, `inputSchema` via `jsonschema`, constraints, risk raised by hints, verify calls must be read-only), `step_calls.py`.
- `approvals.py` (hash binding, two-person rule, starter excluded for destructive), `audit.py` (hash chain, verification), `journal.py` (state change + audit event together).
- `planner.py`, `step_actions.py` + `decisions.py` (typed human decisions and one dispatcher), `runner.py` (one call at a time, lock not held during calls), `rollback.py`, `engine.py` (facade used by Phase 11), `session.py` (per-execution lock, load, save; `ExecutionLimits`), `recovery.py`.
- `store.py` (protocol), `sqlite_store.py` + `sqlite_schema.py`.

Tools (`backend/src/dr_agent/tools/`)
- `base.py` (`ToolExecutor`, `ToolSpec`, `ToolResult` with 16 KB truncation), `dry_run.py`, `fake.py`.

Config and errors
- `EXECUTION_ENABLED`, `EXECUTION_ALLOW_LIVE` (both `false`), `EXECUTION_DB_PATH`, `MCP_SERVERS_FILE`, `EXECUTION_POLICY_FILE`, `EXECUTION_APPROVAL_TIMEOUT_MINUTES`, `EXECUTION_TOOL_TIMEOUT_SECONDS`, `EXECUTION_MAX_TOOL_CALLS`, `EXECUTION_MAX_ACTIVE`; `.env.example` and the README configuration table updated.
- `ExecutionDisabledError` (403), `InvalidTransitionError` (409), `StaleCallError` (409), `PolicyViolationError` (422), `ToolError` (502), already mapped in `api/errors.py`.

Dependencies: `jsonschema` 4.26 (MIT, from the approved design) and `types-jsonschema` (Apache-2.0, dev only, typeshed stubs for `mypy --strict`). `mcp` is added in Phase 10.

## Documentation updated
- `README.md`: status, What it does, Stack, an execution-core architecture sketch, repository layout (`execution/`, `tools/`, `docs/design`, `docs/adr`, scratchpad phases 8 and 9), a new **Runbook execution (in progress)** section (annotation syntax and how a run works), configuration table, Swapping in real integrations (`ExecutionStore`, `ToolExecutor`), roadmap, security notes, and the uv launcher workaround.
- `docs/IMPLEMENTATION_PLAN.md` (Phases 8 and 9), `docs/design/runbook-execution.md` (status, new section 17 with implementation notes), `docs/adr/*` (Accepted).
- `CLAUDE.md` (layout, layering rule, launcher note), `.claude/rules/python-backend.md` and `testing.md`, `.claude/skills/dr-runbook-parser` (annotations, new sample), `.claude/skills/phase-workflow` (phases 8-11).
- `.env.example` (`EXECUTION_*`), `.gitignore` and `.dockerignore` (`executions.db` and its WAL files).

## Decisions and deviations
- P9-1 **Verify calls share the main call's approval.** An approval records the main call's hash and the verify call's hash, and a verify call must be a `read` tool. Editing either call clears the approvals. The design only said "call hash"; this keeps one approval per step without letting an unreviewed verify call run.
- P9-2 **A step without a verify call waits in `VERIFYING`** until a person confirms or reports failure (design table: "or a human confirms"). Step 1 of the executable sample works this way.
- P9-3 **Two transitions added to the design table:** `APPROVED --edit--> AWAITING_APPROVAL` (edits after approval, also used when the pre-run re-check fails) and `VERIFYING --interrupted--> UNKNOWN` (abort or restart during a verify call).
- P9-4 **Rollback state lives on the rollback call.** The step stays `FAILED` until the rollback succeeds (`ROLLED_BACK`). A failed rollback leaves the step `FAILED` with a summary. A rollback in flight at abort or restart is marked "outcome unknown" and the step stays `FAILED`.
- P9-5 **Right before each call** the engine re-checks policy, recomputes the call hash and re-checks the approvals. If any check fails the step goes back to `AWAITING_APPROVAL` and its approvals are cleared (tested with a stricter policy loaded after approval).
- P9-6 **SQLite layout.** `executions.plan_json` holds the full execution document and is what gets loaded. `step_runs`, `tool_calls` and `approvals` are projections written in the same transaction, and `tool_calls` is keyed by (execution, step, kind) rather than a separate id. Every save checks that the new audit events continue the stored chain; a stale writer gets `ConflictError`. **Bug found by the tests:** `INSERT OR REPLACE` deletes the row first, so the `ON DELETE CASCADE` wiped the audit log. It is now an upsert.
- P9-7 **Restart recovery** also pauses `RUNNING` executions that have no call in flight, because nothing drives them after a restart. `CREATED` and terminal executions are left alone.
- P9-8 **Unannotated steps become `AWAITING_MANUAL`** for now. AI proposals (`PROPOSED`, source `ai_proposed`) arrive with the proposer in Phase 10. A step is `PROPOSED` today only when its annotation fails policy.
- P9-9 **Waiting time counts only while the execution runs.** The clock restarts on start and resume. Failures and `UNKNOWN` pause the execution at once.
- P9-10 **Deferred to Phase 11:** approving all read-only steps of a phase in one action (ADR 0003). It is a loop over per-step approvals at the API layer. Also wiring (building the store, executor and engine from settings) and running `recover_interrupted()` in the API lifespan.

## Evidence
- `ruff check backend`: all checks passed. `ruff format --check`: 163 files formatted. `mypy --strict backend/src`: no issues in 94 files.
- `pytest --cov --cov-fail-under=80`: 830 passed, 99.09% total coverage (new modules 88-100%; `rollback.py` lowest).
- Transition tables: `test_execution_transitions.py` compares both tables with an independent copy of the design and checks every (state, event) pair: allowed ones reach the right state, all others raise `INVALID_TRANSITION`.
- Golden report unchanged (`test_golden_report.py` passes, `mock-data/expected-reports/` untouched). The analyzer's phases for the executable sample (`[[1,2],[3],[4],[5]]`, rules only) match the planner's.
- Engine scenarios covered by tests: dry run and live run of the executable sample end to end (9 calls, `COMPLETED`, audit chain valid); disabled and live-not-allowed switches; failure, then a rollback with its own approval; a failed rollback; retry with fresh approval; verify failure; `ToolError`, executor crash and timeout; tool-call limit; capacity cap; approval timeout; manual, skip, reject, convert-to-manual, and edit of main, verify and rollback calls; stale hash; the two-person rule through the engine; abort during a main call and during a rollback call (late results recorded, no state change); restart recovery for main, verify and rollback calls.
- Frontend unchanged: eslint/tsc/prettier clean, 43 vitest tests pass.
- `pip-audit` (locked dependencies, hashes required): no known vulnerabilities. `npm audit --audit-level=high`: 0 vulnerabilities.

## Environment note
On this machine the uv console-script launchers fail with `uv trampoline failed to canonicalize script path` (`mypy.exe`, `pytest.exe`, `pip-audit.exe`, `dr-agent.exe`), so `uv run poe lint`, `poe test` and `poe audit` stop at those subtasks. The gate was run step by step with the same commands through `python -m` (`python -m mypy`, `python -m pytest`, `python -m pip_audit`, `python -m poethepoet`). This is not caused by code changes; `uv sync --reinstall` (recreating the launchers) is the likely fix. CI is unaffected.

## Next (Phase 10, not started)
`tools/mcp_executor.py` and `tools/servers_config.py`, the bundled `mock_mcp` server with fault injection, default `mcp-servers.json` and `execution-policy.json`, and the LLM proposer. Exit: the engine runs the executable sample end to end against the mock server through the SDK's in-memory client.
