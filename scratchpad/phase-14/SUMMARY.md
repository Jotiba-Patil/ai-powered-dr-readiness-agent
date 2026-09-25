# Phase 14 summary: knowledge base

Date: 2026-09-25. Status: done.

## Re-verified first (Phases 0-13)
`uv run poe lint` clean; `uv run poe test` 960 backend tests at 98.84% and 90 UI tests; `uv run poe audit` clean; no file over its size limit; CLI smoke run (`analyze` + `history list`) against a scratch database.

## What was built
- `models/insights.py`: `ServiceHistory`, `StepHistory`, `ExecutionOutcome`, `DependencyTrend` (numbers, enums, timestamps, step numbers and names only).
- `knowledge/`: `fingerprint.py` (normalized action + target system), `durations.py` (active/elapsed minutes and the execution window from audit events), `facts.py` (`build_history`, `for_runbook`, `PastRun`), `rules.py` (HISTORICAL gaps, `Thresholds`), `prompt_facts.py` (the prompt allow-list), `source.py` (`KnowledgeSource` protocol + SQLite), `service.py` (`KnowledgeBase`, `open_knowledge`).
- Core: `GapType.HISTORICAL` (rule-owned), `run_analysis(history=..., history_in_prompt=...)`, `<history>` block, `PROMPT_VERSION = "analysis/2"`, system prompt names `<history>`; `analyze_runbook(knowledge=...)`.
- Report: `historicalInsights` (excluded from JSON when absent, `Field(exclude_if=...)`), terminal and HTML sections.
- API: knowledge base in the lifespan and `AppState`, analyses use it, `GET /api/v1/services/{name}/history`.
- CLI: `analyze` and `execute` use it; `execute` prints a history line and "Previous live runs" per step (`cli_execute_view.py` split out to keep `cli_execute.py` under 200 lines).
- UI: `HistoricalInsights` section, "Previous live runs" on step cards (from the report, no extra request), `previousRuns()`, `makeHistory()` fixture.
- Settings: `KNOWLEDGE_ENABLED`, `KNOWLEDGE_MAX_RUNS`, `KNOWLEDGE_MAX_ANALYSES`, `KNOWLEDGE_IN_PROMPT`.

## Exit criteria
| Criterion | Result |
|---|---|
| A live execution against the mock MCP server produces findings in the next analysis | Done: `integration/test_knowledge_mcp.py` (two live runs, smoke test fails and is rolled back, closed as FAILED; next analysis: "Step 5 failed or was rolled back in 2 of 2 past live runs."; prompt has the counts, not the close reason) |
| Golden report unchanged without history | Done (`estimate-service.json` untouched; HTML snapshot unchanged thanks to Jinja whitespace control) |
| Second golden with a history fixture | Done: `mock-data/expected-reports/estimate-service-history.json` from `backend/tests/fixtures/history/estimate-service.json` (4 HISTORICAL gaps: slow step 2, step 3 failures, RTO over in practice, rates-kafka-topic) |
| Threshold tests for each rule | Done: `test_knowledge_rules.py` (at and around each threshold, minimum samples, custom `Thresholds`) |
| Prompt allow-list enforced by a test | Done: `test_knowledge_prompt_facts.py` (key sets, no summaries/ids/fingerprints, forged `</history>` escaped) |
| Gate | ruff, ruff format, `mypy --strict` (139 files) clean; 1003 backend tests at 98.92%; 94 UI tests (97.06% lines); eslint/tsc/prettier clean; `pip-audit`, `npm audit` clean |

## Decisions and deviations
| # | Decision | Why |
|---|---|---|
| P14-1 | Only finished live executions linked to a stored analysis of the service count; dry runs are only counted | Dry runs measure nothing real; the link gives the service |
| P14-2 | Durations use only event types, state names and timestamps | Payload text is untrusted and not needed |
| P14-3 | Active time runs from the first RUNNING/AWAITING_MANUAL to the last end state (retries included); elapsed starts at the later of run start and first wait | Waiting before the run started is not recovery time |
| P14-4 | Thresholds are code constants (`Thresholds`), not settings | Design listed only four settings; tests pass other values |
| P14-5 | HISTORICAL gaps are rule-owned and raise the rule score; the model's own score is still used when it answers | One scoring path, as before; the model sees the facts and the gaps |
| P14-6 | `historicalInsights` is excluded from JSON when absent | Reports without history stay byte-identical (golden report) |
| P14-7 | The prompt block leaves out execution ids and fingerprints | Meaningless to the model; less to leak |
| P14-8 | Step cards get history from the report, not from `GET /services/{name}/history` | The report's steps are already matched to this runbook's numbers |
| P14-9 | Reading history never fails an analysis (`insights_for` returns None on storage errors) | Same rule as saving (Phase 13) |
| P14-10 | Dependency "unhealthy" = DOWN or UNREACHABLE; design's DEGRADED and Markdown format do not exist here | Match the real enums and formatters |

## Notes
- The mock environment's timings are simulated, so duration findings in the PoC demonstrate the mechanism, not real recovery times.
- The Docker run is still pending as in Phases 7, 11 and 13 (Docker is not installed on this machine); compose only gained two environment variables.
- Later work (design section 11): embeddings for fuzzy step and dependency matching, cross-runbook shared dependencies.

## Follow-up (2026-09-25, owner feedback after trying the dashboard)
1. **"Create live run" was disabled.** Not a code bug: the rule is "enabled until a live run of this analysis completes", and the demo server ran without `EXECUTION_ALLOW_LIVE=true`. Restarted with it; the browser showed both buttons enabled on a fresh analysis. New tests pin the rule (FAILED or ABORTED live run: still enabled; COMPLETED: disabled, "Live run completed.").
2. **History tab showed "Execute this runbook…".** Replaced by "Executions of this analysis": the runs of the stored analysis and, for a chosen run, its steps (locked cards, no actions) and its audit log with the chain verified. New endpoint `GET /api/v1/analyses/{id}/executions/{executionId}` (works while execution is off, `404` for another analysis's run), `History.execution()`, `StoredExecution` schema, `usePastExecutions`, `PastExecutions`, optional `maxToolCalls` on `ExecutionHeader`. The API and `dr-agent execute --analysis ID` can still execute a stored analysis; the dashboard runs only fresh analyses.
- Gate: ruff, `mypy --strict` clean; 1004 backend tests at 98.92%; 99 UI tests (95.93% lines); eslint/tsc/prettier clean; no file over its limit. Browser check (Playwright MCP): History -> open analysis -> run -> 5 read-only step cards, "Hash chain verified: 53 events"; Analyze -> new analysis -> both create buttons enabled.
3. **No feedback while buttons were disabled.** Creating a run can take minutes (the AI proposes a call for each step without a `Tool:` annotation). `useExecution.run(action, progress)` now carries a label (and an optional hint) for every pending request: "Creating the live run…", "Recording your approval of step 3…", "Starting the run…", and so on. `ProgressNote` shows it with a spinner and elapsed seconds (role `status`). While the server calls tools in the background (`callingTools()`: execution RUNNING and a step RUNNING or verifying with a verify call), a "Run in progress" note is shown; it is not shown while the run waits for a person. Tests: `ExecutionProgress.test.tsx` (4). UI tests 103 pass; under heavy Ollama CPU load several unrelated UI tests hit vitest's 5 s timeout, and all pass with `--testTimeout=30000`.
4. **"Mark done" disabled on a new order-service live run.** The API log shows `POST /executions` took 582 s: none of the 6 order-service steps has a `Tool:` annotation, so the server asked the local model (qwen2.5:3b on CPU) for a proposal per step, one after another; all answered "manual step". Every step button is disabled while a request is pending, and at that time there was no progress note (added in item 3). After creation the buttons are enabled: reproduced with the same state in a test and checked in the browser (new live run: Approve, Edit call, Reject and Skip enabled; the server accepts Mark done before Start). Safeguard added: with an empty "Your name" the panel now says why the step buttons are disabled. Tests: `ManualSteps.test.tsx` (2). UI tests: 105 pass. Tip: `EXECUTION_AI_PROPOSALS=false` makes unannotated steps manual immediately.
5. **A finished live run stayed on screen while a new dry run was being created.** `create` in `ExecutionSection` now clears the shown execution before sending the request; the progress note is shown alone, the list of runs stays, and the new run appears when created. Test in `ExecutionProgress.test.tsx`. UI tests: 106 pass (twice in a row); one earlier full run had a one-off failure in the existing "runs the demo path" test that did not recur.
   Question answered: every execution, dry or live, is stored with its analysis (`executions.analysis_id`, steps, calls, approvals, hash-chained audit) and shown read-only in the History tab; the knowledge base measures only finished live runs and only counts dry runs.
6. **UI redesign ("looks very simple and AI generated").** Problems found on screen first: one 5000+ px scroll with the input always open; the verdict buried in a small gauge; execution as a log of tall JSON cards with Start/Abort at the very bottom; no identity or server context. Changes (Tailwind v4 only, no new dependencies):
   - Theme in `index.css` (`ink-*`, `signal-*`, `card`, `btn-primary`, `btn-ghost`, `tabular`), inline icon set `components/ui/Icon.tsx`, new favicon.
   - `shell/AppHeader.tsx` + `useServerStatus` (new `api.health()`): product mark, Analyze/History tabs, "API online · v0.1.0" and execution chips (off / dry runs only / live runs enabled).
   - `JourneySteps` (runbook -> report -> execution); the input folds into a one-line bar once a report exists ("Analyze another runbook"); pasted input is named "pasted runbook" instead of `request-body.md`.
   - `report/VerdictHero.tsx` + `lib/verdict.ts`: verdict sentence, key-figure tiles (recovery time, dependencies, gaps, SPOFs, track record) that jump to their sections, summary prose; section chips; sections get icons and anchors.
   - Execution: option cards for dry vs live, `RunProgress` + `lib/runProgress.ts` inside the run header, run controls moved above the steps and sticky, step timeline (`StepCard` rail with state-coloured numbered dots), readable audit log, dark loading card.
   - History: styled table (service + runbook, risk badge, RTO colour, runs chip), buttons instead of underlined links.
   - Accessible names kept, so the existing tests pass unchanged; new `Redesign.test.tsx` (6). UI tests 112 pass (96.3% lines); lint clean; `poe build-ui` OK. Browser screenshots in `.playwright-mcp/ui-v2-*.png`. Known: Recharts logs a harmless size warning when the RTO chart renders while the Analyze tab is hidden.
7. **Journey and start over.** The Execution stage now ticks when a run of the analysis on screen has completed ("Run in progress" once a run exists): `ExecutionSection` reports a stage (`none` / `started` / `done`, a primitive so the page re-renders only when it changes) through `ExecuteRunbook` to `AnalyzeView`. "Analyze another runbook" now starts over: `useAnalysis.reset()`, stage back to `none`, and a new key on `InputPanel` for empty editors; the report and the execution section disappear and the journey returns to step 1. Tests in `Redesign.test.tsx` (8 now); UI tests 114 pass; lint clean. Not re-checked in the browser (the hot reload cleared the page and a completed run needs a new model analysis plus approvals); the tests drive the same components.
