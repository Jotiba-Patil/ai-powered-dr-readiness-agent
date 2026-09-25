# Phase 13 summary: analysis history

Date: 2026-09-25. Status: done except the Docker run (Docker is not installed on this machine, as in Phases 7 and 11).

## What was built
- `storage/`: shared SQLite connection helper and numbered migrations (1 = executions, 2 = `analyses` + `executions.analysis_id`).
- `history/`: `AnalysisRecord` / `AnalysisSummary` / `AnalysisQuery`, `AnalysisStore` protocol, SQLite store, `History` service (save never raises, retention, staleness, linked executions), `open_history()`.
- API: `routes_history.py`, `schemas_history.py`, `analysis_lookup.py` (memory first, then history; the `JobStore` save hook); `HistoryDisabledError` (403).
- CLI: `cli_common.py`, `cli_analysis.py`, `cli_history.py`; `analyze --no-save`; `execute --analysis ID`.
- UI: History tab (`components/history/`), `ExecuteRunbook`, `useHistory`, `useStoredAnalysis`, `historyClient.ts`, "Saved to history" note.
- Delivery and docs: Docker `DB_PATH` and `dr-agent-data` volume, ignore files, `.env.example`, README, CLAUDE.md, rules, design section 13.

## Gate
- ruff, ruff format, `mypy --strict` (129 files): clean
- pytest: 960 passed, coverage 98.84% (was 911)
- vitest: 90 passed (was 78), 96.99% lines; eslint, tsc, prettier clean
- `pip-audit`, `npm audit`: no vulnerabilities
- Browser drill (Playwright MCP): analyze -> saved -> API restart -> History -> open -> dry run from the stored analysis -> run count 1
- `uv run poe` launchers were broken at the start; `uv sync --reinstall` fixed them

## Decisions and deviations
| # | Decision | Why |
|---|---|---|
| P13-1 | The job is saved before it is marked `succeeded` | A client that sees "succeeded" can immediately execute it, and the execution's foreign key finds the analysis |
| P13-2 | `executions.analysis_id` is filled with a sub-select, so it stays empty when the analysis was not stored | Executions of unsaved analyses (history off, `--no-save`) must keep working |
| P13-3 | Migrations run each step in an explicit `BEGIN IMMEDIATE` transaction | Python's `sqlite3` does not wrap DDL in a transaction by itself |
| P13-4 | Retention runs at startup and after each save, not daily | No scheduler needed |
| P13-5 | Default DB file `dr-agent.db`; `EXECUTION_DB_PATH` still read | One file for both; old setups that set the variable keep their data |
| P13-6 | Docker volume renamed `dr-agent-data` | Docker has never run on this machine, so there is no data to migrate; name matches the content |
| P13-7 | `history list` prints plain lines, not a Rich table | Rich squeezed the 32-character id in narrow or non-TTY output; plain lines are copyable and pipeable |
| P13-8 | Service filter applies on form submit | Exact match, so per-keystroke requests were useless |
| P13-9 | Risk badge in the history table shows "72 High" | Color and icon alone would break the accessibility rule |
| P13-10 | `backend/tests/conftest.py` sets `DB_PATH` to `tmp_path` for every test | History is on by default and must never write into the repository |

## Notes for Phase 14
- `History.executions()` filters `list_all()` in Python; fine for the PoC, but the knowledge base should query `step_runs` / `audit_events` by `analysis_id` directly. *Done: `knowledge/source.py` joins `executions` to `analyses` in SQL.*
- The earlier one-off "I/O operation on closed file" logging failure appeared only with a `-k` subset ordering and never in full runs; not caused by this phase. *Not seen again in any Phase 14 run.*
