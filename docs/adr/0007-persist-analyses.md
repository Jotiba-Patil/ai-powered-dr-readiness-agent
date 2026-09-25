# 0007. Persist analyses in the SQLite store, linked to executions

- Status: Accepted (2026-09-25)
- Date: 2026-09-25
- Related: [design](../design/analysis-history.md) sections 3-5; partly supersedes [ADR 0004](0004-sqlite-execution-store.md) ("analysis jobs stay in memory")

## Context

ADR 0004 kept analysis jobs in memory because losing them seemed harmless. Since executions must follow an analysis (post-Phase-11 change), that is no longer true: an execution points to an analysis that disappears on restart, users cannot reopen earlier reports, and no knowledge can be built from past results. The project owner asked on 2026-09-25 for analyses to be stored with the execution details.

## Decision

- Store every **successful** analysis in a new `analyses` table in the **same SQLite file** as executions, with the analysis job id as its primary key.
- Add a nullable `executions.analysis_id` foreign key (`ON DELETE RESTRICT`). Executions from before the change keep `NULL`.
- Introduce numbered schema migrations in a shared `storage/` package; today's schema is version 1, this change is version 2. A newer database version than the code knows is refused at startup.
- An `AnalysisStore` protocol in `history/` with a SQLite implementation, injected like `ExecutionStore`. `JobStore` saves through an injected `on_success` callback; failing to save is logged and flagged on the job but never fails the analysis.
- The database setting becomes `DB_PATH` (default `dr-agent.db`), with `EXECUTION_DB_PATH` read as a fallback. `HISTORY_ENABLED` (default `true`) turns saving off.
- Analyses are kept until deleted, or until `HISTORY_RETENTION_DAYS` if set; an analysis with executions cannot be deleted.

## Consequences

- Reports survive restarts; any stored analysis can be reopened, exported or executed again.
- The audit trail of an execution can always be traced to the exact report and runbook it followed.
- The database grows with every analysis (roughly the runbook size plus 10-50 KB of JSON). Retention is available but off by default.
- The database file now matters even with execution disabled, and holds sensitive text (see ADR 0008).
- Migration code must be maintained and tested against real version-1 files.

## Alternatives considered

- **A separate database file for analyses.** Simpler migrations, but no foreign key between executions and analyses, and two files to back up.
- **JSON files per report.** No transactions, no queries by service or risk.
- **PostgreSQL.** Better for several API instances, but an extra service for a single-instance PoC; the store protocol keeps this open.
- **Keep jobs in memory and store only a report snapshot inside each execution.** Covers only analyses that were executed, which rules out a knowledge base.
