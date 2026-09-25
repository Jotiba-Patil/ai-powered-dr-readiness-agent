# Design: analysis history and DR knowledge base

| | |
|---|---|
| Status | Accepted 2026-09-25 (Phase 12 reviewed by the project owner) |
| Date | 2026-09-25 |
| Phases | 12 (this document, done), 13 (analysis history, done, see section 13), 14 (knowledge base, done, see section 14), see [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) |
| Decisions | [0007](../adr/0007-persist-analyses.md), [0008](../adr/0008-store-raw-runbook.md), [0009](../adr/0009-knowledge-base-measured-facts.md) |

## 1. Context

Analyses live only in memory (`api/jobs.py` `JobStore`, capped at `API_MAX_STORED_JOBS`), and the CLI keeps nothing. Executions, their approvals and their audit logs are already stored in SQLite ([ADR 0004](../adr/0004-sqlite-execution-store.md)), but they point to an analysis job id that disappears on restart. The result:

- A user cannot go back to the report an execution followed, or to any earlier report.
- After a restart, no execution can be started from an earlier analysis (design `runbook-execution.md`, section 17, "Limit").
- What past drills and failovers actually showed (real step durations, failures, rollbacks) is never used again.

Decisions made with the project owner on 2026-09-25:

- Store every finished analysis **together with the raw runbook Markdown**, linked to the executions created from it.
- Build a **knowledge base** from that history for future analyses and for recovery.
- The knowledge base may feed **only facts measured by code** into LLM prompts, never past model text or tool output.
- Design first (this phase), then build history (Phase 13), then the knowledge base (Phase 14).

## 2. Goals and non-goals

**Goals**
- Keep every successful analysis (report, parsed runbook, raw Markdown, inventory, how it was produced) across restarts.
- List, filter, open and export past analyses from the API, CLI and UI, each with the executions created from it.
- Start an execution from any stored analysis, not only from one still in memory.
- Derive per-service facts from history (measured durations, step outcomes, rollbacks, dependency health trends) and use them in the report, in the LLM prompt and during execution.

**Non-goals**
- Authentication, per-user access control or multi-tenancy (still a PoC; see section 10).
- Semantic search or embeddings. Phase 14 matches by service and step identity; embeddings are later work (section 11).
- Storing failed analyses. A failed job has no report; its error stays in memory as today.
- A database server. SQLite remains the only store.
- Changing deterministic results: history adds findings, it never changes the RTO sum, dependency health or the risk-level mapping.

## 3. Architecture

```
            API (routes_history.py)      CLI (cli_history.py)       UI (History view)
                      \                        |                        /
                       +------ service.py / history/service.py -------+
                                 |                          |
                     history/ (AnalysisStore)       knowledge/ (facts)
                                 \                          /
                              storage/ (one SQLite file, migrations)
                                 /
                     execution/ (ExecutionStore, unchanged protocol)
```

- **`storage/`** (new, framework-free): `sqlite.py` (connection helper with the WAL, foreign-key and busy-timeout pragmas now in `execution/sqlite_store.py`) and `migrations.py` (ordered, numbered migrations; version 1 is today's execution schema). Both stores open the same file through it.
- **`history/`** (new, framework-free): `models.py` (`AnalysisRecord`, `AnalysisSummary`, `AnalysisQuery`), `store.py` (`AnalysisStore` protocol), `sqlite_store.py`, `service.py` (save and look up, builds records from a finished job).
- **`knowledge/`** (Phase 14, framework-free): `models.py` (`ServiceHistory`, `StepHistory`, `HistoricalFinding`), `facts.py` (computes facts from stored executions and analyses), `rules.py` (history-based gaps), `prompt_block.py` data only (the prompt text itself stays in `llm/prompts/`).
- **Injection:** stores are created in the composition roots (`api/app.py` lifespan, CLI startup, `execution_runtime.py`) and passed in. `JobStore` gets an optional `on_success` callback that saves the record, so `api/jobs.py` stays storage-agnostic. `core/analyzer.py` receives history facts as an optional argument and never opens a database.

## 4. Data model

One SQLite file holds analyses and executions, so the link can be a real foreign key. It is needed even when execution is off, so the setting becomes `DB_PATH` (default `dr-agent.db`, Docker `/data/dr-agent.db`); `EXECUTION_DB_PATH` is still read as a fallback so existing setups keep their file. `.gitignore` and `.dockerignore` gain `*.db`.

### 4.1 New table `analyses` (migration 2)

| Column | Notes |
|---|---|
| `id` TEXT PK | The analysis job id, so existing `analysisJobId` values keep working |
| `service_name`, `owner` | From the parsed runbook; `service_name` is indexed |
| `created_at`, `completed_at` | Job timestamps (UTC ISO 8601); `completed_at` is indexed |
| `source` | `api` or `cli` |
| `runbook_label`, `runbook_sha256`, `runbook_markdown` | Raw text, see [ADR 0008](../adr/0008-store-raw-runbook.md) |
| `inventory_label`, `inventory_json` | Inventory as validated (nullable when none was given) |
| `risk_score`, `risk_level`, `rto_feasible`, `ai_analysis_available` | Copied out of the report for filtering and sorting |
| `llm_provider`, `llm_model`, `prompt_version`, `agent_version` | How the report was produced; never the API key or base URL credentials |
| `runbook_json`, `report_json` | Parsed `Runbook` and full `DRReadinessReport`, validated again on load |

### 4.2 Change to `executions` (migration 2)

- Add `analysis_id TEXT REFERENCES analyses(id)`, nullable, indexed. New executions always set it.
- Executions created before migration 2 keep `NULL`: their analyses were never stored. `Execution.analysis` in `plan_json` is unchanged.
- An analysis that has executions cannot be deleted (the audit trail must keep its source). `ON DELETE RESTRICT`.

### 4.3 Migrations

- `schema_version` holds the highest applied migration. At startup each missing migration runs in its own transaction, in order. Today's databases are version 1.
- A database with a version newer than the code knows is refused with a `ConfigError` (fail fast, no silent downgrade).
- Tests migrate a version-1 file with executions in it and check nothing is lost.

## 5. Behaviour

### 5.1 Saving
- **API:** when a job succeeds, `on_success` writes the record in one transaction. A write failure is logged and shown on the job as `historySaved: false`; the report itself is still returned (storage must not break analysis).
- **CLI:** `analyze` and `execute` save by default; `analyze --no-save` skips it. `execute` must save, because the execution needs the stored analysis.
- **Off switch:** `HISTORY_ENABLED=false` stores nothing, and the history endpoints answer `403 HISTORY_DISABLED`. Execution then still works for analyses in memory, as today.
- Only successful analyses are saved. Nothing is logged from the runbook text (unchanged rule).

### 5.2 Reading and executions
- `GET /dr/jobs/{id}` falls back to the store when the job is no longer in memory, so a reloaded dashboard keeps working after a restart.
- `POST /executions {analysisJobId}` looks in memory first, then in the store. After a restart, any stored analysis can be executed again. The execution still follows that report's plan; a warning is shown when the analysis is older than `HISTORY_STALE_AFTER_HOURS` (default 24), because dependency health may have changed.

### 5.3 Retention
- Kept until deleted. `HISTORY_RETENTION_DAYS` (default `0`, meaning keep forever) deletes older analyses that have no executions at startup and once a day.
- `DELETE /analyses/{id}` removes one analysis; `409` if executions refer to it.

## 6. HTTP API (Phase 13)

New router `api/routes_history.py` under `/api/v1`. Pydantic views, shared error shape.

| Method and path | Purpose |
|---|---|
| `GET /analyses?service=&riskLevel=&limit=&before=` | Newest first, keyset pagination on `completedAt` (`limit` max 100). Summaries only: id, service, time, risk, RTO feasible, AI available, execution count |
| `GET /analyses/{id}` | Summary plus full report, inventory label and production metadata |
| `GET /analyses/{id}/runbook` | Raw Markdown as `text/plain; charset=utf-8` with `Content-Disposition: attachment` |
| `GET /analyses/{id}/report.html` | Same HTML rendering and CSP as the job report |
| `GET /analyses/{id}/executions` | Executions created from it (summary view) |
| `DELETE /analyses/{id}` | `204`; `409` when executions exist |
| `GET /services/{name}/history` | Phase 14: the knowledge-base facts for one service |

New error: `HISTORY_DISABLED` (403). Unknown ids are `404 NOT_FOUND` as today. `poe gen-api` refreshes the frontend client.

## 7. CLI (Phase 13)

- `dr-agent history list [--service NAME] [--limit N]`: Rich table.
- `dr-agent history show ID [--format terminal|json|markdown|html] [--runbook]`: reuses the existing formatters; `--runbook` prints the stored Markdown.
- `dr-agent history delete ID`: asks for confirmation.
- `dr-agent execute --analysis ID`: executes a stored analysis instead of analyzing again. It still prints the risk, RTO, gaps and plan and asks first, so "execution always follows an analysis" holds.

## 8. User interface (Phase 13, extended in 14)

- A **History** view next to Analyze (two tabs, no router, as the old Execute tab was built). A table of past analyses with filters by service and risk level, and an execution count per row.
- Opening a row shows the existing `ReportView` plus `ExecutionSection` (runs of that analysis, start a new one), with "Download runbook" and "HTML report" links. An "analysed N hours ago" banner warns when stale.
- After an analysis finishes, the report shows "Saved to history" (or a warning if saving failed).
- Phase 14 adds a **History** section to the report (section 9.3) and a "previous runs" line on each execution step card.

## 9. Knowledge base (Phase 14)

See [ADR 0009](../adr/0009-knowledge-base-measured-facts.md).

### 9.1 Facts (computed by code only)
For one service, from its stored analyses and **live** executions (dry runs measure nothing real and are excluded; a count of them is shown):

- **Per step:** runs, outcome counts (`SUCCEEDED`, `FAILED`, `ROLLED_BACK`, `SKIPPED`, `MANUAL_DONE`, `UNKNOWN`), retries, rollbacks, median and max **active** minutes (entering `RUNNING` or `AWAITING_MANUAL` to its end state) and **elapsed** minutes (including approval waits), all read from audit event timestamps.
- **Per execution:** end state and total elapsed minutes, compared with the stated RTO of the analysis it followed.
- **Per dependency:** status in each past analysis (how often it was `DOWN`, `DEGRADED` or `UNREACHABLE`).
- **Per analysis:** risk score trend.

Allowed values are numbers, enums, timestamps, step numbers and identifiers that already come from the runbook or inventory (service, target-system and dependency names, tool names). Excluded: step summaries, tool results, errors, rationales, comments, reasons and any report prose.

### 9.2 Matching steps across runbook versions
A step's identity is `(service_name, fingerprint)`, where the fingerprint is the SHA-256 of the normalized action text (lower case, collapsed whitespace, digits kept) plus the target system. When the runbook changes a step's wording, it starts a new history. That is deliberate: exact matching gives no false merges. Fuzzy matching is later work (section 11). Minimum sample sizes before a finding is raised: 2 live runs for durations, 3 analyses for dependency trends (configurable).

### 9.3 Where facts are used
1. **Rule-based gaps** (`knowledge/rules.py`, deterministic, like `core/gap_rules.py`), for example:
   - A step's median measured time exceeds its estimate by more than 50%.
   - The measured total of the last live runs exceeded the stated RTO while the plan claims it is feasible.
   - A step failed or was rolled back in at least half of its live runs.
   - A dependency was unhealthy in at least half of the recent analyses.
   These need a new `GapType` value (`HISTORICAL`) and add to the risk score through the existing scoring, so the golden report stays the same when there is no history.
2. **Report section** `historicalInsights` (optional, omitted when empty): the facts and findings above, shown in the UI, terminal, Markdown and HTML formats.
3. **LLM prompt:** the same facts as escaped JSON in a `<history>` block, described in the system prompt as measured data. Prompt versions are bumped. The model may use it in reasoning; the facts in the report always come from code.
4. **During execution (recovery):** each step card and CLI step panel show "previous live runs: 4, failed 1, rolled back 1, median 12 min". `GET /services/{name}/history` serves it. It is information only: it never approves, skips or changes a call.

### 9.4 Configuration
`KNOWLEDGE_ENABLED` (default `true` when history is on), `KNOWLEDGE_MAX_RUNS` (most recent live executions considered, default 10), `KNOWLEDGE_MAX_ANALYSES` (default 20), `KNOWLEDGE_IN_PROMPT` (default `true`).

## 10. Security notes

- **Sensitive data at rest.** The raw runbook and inventory may contain hostnames, IPs and internal procedures. The database file is sensitive: gitignored, excluded from Docker build contexts, on the named volume only. There is no encryption at rest (PoC); use disk encryption. Stored text is still never logged.
- **No authentication.** Anyone who can reach the API can read every stored runbook. This widens the existing "keep the API on localhost or behind an authenticating proxy" limit, and the README says so.
- **Rendering.** Stored Markdown is served as `text/plain` attachment and shown in the UI as text, never rendered as HTML. HTML reports use the existing autoescaping and CSP.
- **Prompt injection through history.** Past runbooks could contain injection text; that is why only code-measured facts reach prompts (section 9.1) and each is escaped JSON inside `<history>`. Identifier strings from the runbook are already sent in `<runbook>` today, so no new kind of text reaches the model.
- **Rule change.** `.claude/rules/llm-and-security.md` ("Never feed tool results or rationales back into a prompt") gains an explicit exception for the section 9.1 facts, in Phase 14, together with a test that the `<history>` block contains no free text fields.
- **Input.** Query parameters are validated (ids as hex, `limit` bounded, service names length-capped). SQL uses parameters only.

## 11. Later work

- Embeddings for fuzzy matching of steps, dependency names and similar runbooks (discussed 2026-09-25; not in scope).
- Comparing runbooks across services to find shared dependencies.
- Postgres behind the same store protocols for more than one API instance.
- Encryption at rest and per-user access once authentication exists.
- Storing failed analyses for troubleshooting.

## 12. Testing strategy

- Unit: migrations (fresh file, version-1 file with data, newer version refused), `AnalysisStore` round trip and filters, keyset pagination, retention, delete refused with executions, fact computation from hand-built executions and audit events, step fingerprints, each history rule at and around its threshold, the `<history>` block containing only allowed fields.
- Integration: API analyze then restart (new app on the same file) then `GET /analyses`, `GET /dr/jobs/{id}` and `POST /executions`; CLI `analyze`, `history list/show`, `execute --analysis`; a live execution against the mock MCP server feeding the next analysis's findings.
- Golden report unchanged with no history; a second golden report with a fixed history fixture.
- UI: History view list, filters, opening a report, stale banner, report history section (vitest + RTL). Browser drill extended with a restart.
- Tests use `tmp_path` database files; no test shares a database.

## 13. Implementation notes (Phase 13)

Details and decisions P13-1 to P13-10 are in [scratchpad/phase-13/SUMMARY.md](../../scratchpad/phase-13/SUMMARY.md). Differences from the sections above:

- **Retention** runs at startup and after each save, not on a daily timer (section 5.3): no scheduler is needed, and a busy server prunes more often than daily anyway.
- **`dr-agent history list`** prints one plain line per analysis instead of a Rich table: the 32-character id stays whole and copyable, and the output can be piped.
- **`stale`** is computed by the server (`GET /analyses/{id}`) and by the CLI from `HISTORY_STALE_AFTER_HOURS`; the UI only shows it.
- **The service filter is an exact match**, applied when the user submits the filter form (no request per keystroke).
- **The default database file** is `dr-agent.db` when neither `DB_PATH` nor `EXECUTION_DB_PATH` is set. A local setup that relied on the old default `executions.db` without setting the variable starts a new file; set `EXECUTION_DB_PATH=executions.db` to keep it. Docker uses `/data/dr-agent.db` on the renamed `dr-agent-data` volume.
- **`execution/sqlite_store.py`** now writes `analysis_id` only when that analysis is stored (a sub-select), so executions from analyses that were not saved still work, with the link left empty.
- `GET /services/{name}/history` (section 6) is Phase 14 work.
- **After Phase 14 (owner request, 2026-09-25): the History tab is read-only.** Section 8 had an opened analysis offer "Execute this runbook…". It now shows "Executions of this analysis" instead: the runs, and for a chosen run its steps (locked cards, no actions) and its verified audit log, through the new `GET /analyses/{id}/executions/{executionId}` (answers while execution is off, `404` for another analysis's run). New runs start only from a fresh analysis on the Analyze tab, so they follow current dependency health; the API and `dr-agent execute --analysis ID` can still execute a stored analysis.

## 14. Implementation notes (Phase 14)

Details and decisions P14-1 to P14-10 are in [scratchpad/phase-14/SUMMARY.md](../../scratchpad/phase-14/SUMMARY.md). Differences from section 9:

- **Dependency status values** are the ones the inventory really has: `UP`, `DOWN`, `UNREACHABLE`, `NOT_IN_INVENTORY` (section 9.1 mentioned `DEGRADED`, which does not exist). "Unhealthy" means down or unreachable.
- **Formats:** the report formats are JSON, terminal and HTML (section 9.3 mentioned Markdown, which the project does not have).
- **Thresholds** live in `knowledge/rules.py` (`Thresholds`, used by tests), not in settings: 2 live runs, 3 analyses, 1.5 x estimate, 50% shares. Only `KNOWLEDGE_ENABLED`, `KNOWLEDGE_MAX_RUNS`, `KNOWLEDGE_MAX_ANALYSES` and `KNOWLEDGE_IN_PROMPT` are settings, as section 9.4 lists.
- **Risk score:** HISTORICAL gaps are rule-owned and count in the rule-based score, which is the score whenever the model is unavailable. When the model answers, its own score is used as before (it sees the history and the HISTORICAL gaps in `rulesAlreadyChecked`); the gaps are listed either way.
- **Report section** `historicalInsights` is `ServiceHistory` matched to the analyzed runbook (current step numbers and estimates). It is excluded from the JSON when absent, so reports without history are byte-identical to before (golden report unchanged).
- **Durations:** active = first `RUNNING` or `AWAITING_MANUAL` until the step's last end state (retries included); elapsed starts at the later of "run started" and "step first waited for a person". Executions that never started or did not finish give no outcome.
- **The prompt block** leaves out execution ids and fingerprints (identifiers without meaning to the model).
- **`GET /services/{name}/history`** returns steps keyed by fingerprint, not matched to any runbook.
- **Two knowledge-disabled paths:** `KNOWLEDGE_ENABLED=false` (history still stored) and `KNOWLEDGE_IN_PROMPT=false` (facts still reported and used in rules, but not sent to the model).
