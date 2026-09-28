# Phase 17 summary: schedules API, UI, CLI and delivery

Date: 2026-09-27. Status: done. Exit criteria met except the Docker run (Docker is not installed on this machine, as in Phases 7, 11 and 13). Not committed (owner asked for no commits).

## Before starting
Re-verified Phases 0-16: ruff clean, 272 files formatted, `mypy --strict` no issues in 156 files, eslint/tsc/prettier clean; 1123 backend tests at 99.01%, 114 UI tests (97.25% lines); `pip-audit` and `npm audit` clean.

## What was built
| Area | Files |
|---|---|
| Runtime wiring | `scheduling_runtime.py` (`open_schedules()`), `api/scheduled_jobs.py` (`job_analyzer()`: `JobStore` job with `source=scheduled`, cancelled with its task), `api/app.py` lifespan (open, start, stop before the job store; `notifier` parameter), `api/deps.py` (`AppState.schedules`) |
| API | `api/routes_schedules.py` (list, create, read, update, delete, pause, resume, run now, runs), `api/routes_scheduler.py` (state, pause all, resume all, recipient preview, one run, cancel), `api/schemas_schedules.py`; `poe gen-api` refreshed `frontend/openapi.json` and `schema.d.ts` |
| Scheduling additions | `RunEmailer.recipients()` (shared by sending and preview), `Scheduler.emailer` public, `ScheduleService.preview_recipients()` |
| CLI | `cli_schedule.py`: `dr-agent schedule list`, `schedule runs ID` (read-only) |
| UI | Schedules tab: `components/schedules/` (`SchedulesView`, `ScheduleList`, `ScheduleForm`, `CadenceFields`, `RecipientLine`, `PauseForm`, `SchedulerBar`, `ScheduleRuns`, `ScheduledRunDetail`, `YourName`), `api/scheduleClient.ts`, `hooks/useSchedules.ts`, `hooks/useScheduleRuns.ts`, `lib/scheduleLabels.ts`; `App.tsx` (email-link hash on load and `hashchange`), `AppHeader` (tab), `Section` (icons), `api/types.ts`, `test/scheduleFixtures.ts`, `test/fixtures.ts` |
| Delivery | `docker-compose.yml`: `mailpit` (`axllent/mailpit:v1.31.3`, hardened) on the new internal `mail` network with `api`, web inbox on `127.0.0.1:8025`; api scheduler and notify settings (`NOTIFY_TRANSPORT=smtp`) |
| Docs | design section 17 and status; `docs/IMPLEMENTATION_PLAN.md` (Phase 17 and Verification); README (feature list, Docker, dashboard item 7, CLI, schedule API table, new "Scheduled analysis" section, roadmap); `docs/SECURITY_GUARDRAILS.md` section 7; `CLAUDE.md` (commands, execution rule); `.claude/rules/frontend-react.md`, `testing.md`, `python-backend.md`; phase-workflow skill |

## Tests
- Backend, 24 new: `integration/test_api_schedules.py` (disabled `403` on four routes, CRUD with the server default timezone, 7 validation and path cases, schedule limit, run now → stored `source=scheduled` → emailed owner → run pages, unknown ids); `integration/test_api_schedule_control.py` (pause until and its limit, pause all without leaking the SMTP password, cancel with no email and a second cancel `409`, recipient preview including the domain allow-list and path traversal, a dry run created from a scheduled run with the existing `POST /executions`, real SMTP delivery to an in-process `aiosmtpd`, shutdown marks a running run `INTERRUPTED`); `integration/test_cli_schedule.py`; `test_api_platform.py` path list; helper `integration/schedule_api_support.py`.
- UI, 23 new: `api/scheduleClient.test.ts`, `components/schedules/SchedulesView.test.tsx`, `ScheduleForm.test.tsx`, `lib/scheduleLabels.test.ts`, `App.schedules.test.tsx`.
- Browser drill: `DRILL.md` in this folder, with `drill-dry-run-from-scheduled-run.png` and `drill-paused.png`.

## Gate (final run)
| Check | Result |
|---|---|
| `uv run poe lint` | ruff clean, 282 files formatted, `mypy --strict` no issues in 162 files, eslint/tsc/prettier clean |
| `uv run poe test` | 1147 backend tests passed, 98.96%; 137 UI tests passed, 96.55% lines |
| `uv run poe audit` | no known vulnerabilities; npm 0 vulnerabilities |
| File sizes | backend files under 200 lines, components under 150; only the generated `schema.d.ts` is larger |
| Docker | not installed; `docker-compose.yml` parsed with PyYAML (services api, mailpit, mock-mcp, ui; internal `tools` and `mail` networks); CI `docker` job builds and starts it |

## Decisions made while building (open for review)
| # | Decision | Why |
|---|---|---|
| P17-1 | The scheduler stops before the job store at shutdown | Otherwise a running run fails with a cancelled job and sends a failure email; now it ends as `INTERRUPTED` with no email |
| P17-2 | Pausing and resuming one schedule are `POST /schedules/{id}/pause` and `/resume`, not fields of `PUT` | A pause needs a name and its own limits; `PUT` stays a plain replace of the settings |
| P17-3 | Recipient preview at `GET /api/v1/scheduler/recipient-preview` | `/schedules/recipient-preview` would be taken by `/schedules/{id}` |
| P17-4 | A scheduled run's report offers the normal `ExecuteRunbook`; the frontend rule now names this as the second place an execution can start | Owner requirement ("user can execute from the list of scheduled jobs"); still created from an analysis, still approval-gated |
| P17-5 | Email links are read on load and on `hashchange`; "Back to schedules" clears the hash | Found in the drill: a link opened in an already open tab did nothing |
| P17-6 | The CLI reads schedules straight from the database and works while the scheduler is off (with a note) | Useful for inspection; changes stay in the API and UI, where the scheduler runs |
| P17-7 | `create_app(notifier=...)` for tests, `schedule_client(capture=False)` for real SMTP | Deterministic email assertions without a mail server; one test still speaks real SMTP |
| P17-8 | Mailpit pinned to `v1.31.3` (checked on Docker Hub), hardened like the other services; SMTP only on the internal `mail` network | Same hardening as the rest; the demo inbox is the only published port |
| P17-9 | The create form clears name and recipients after success; runbook, cadence and timezone stay | Makes a second, similar schedule quick without resubmitting the first by accident |
| P17-10 | The browser drill used `aiosmtpd` instead of Mailpit | Docker is not available here; the SMTP exchange and the email content are the same |

## Documentation follow-up (owner review, 2026-09-27)
The owner asked to check for files that were missed. `docs/IMPLEMENTATION_PLAN.md` already had Phase 17 on disk (an editor tab opened earlier may show the old text). A section-by-section check found these gaps, now fixed:
- README "Architecture": a scheduler paragraph and flow diagram, Mailpit in the Compose diagram and the paragraph under it.
- README "Repository layout": `scheduling_runtime.py`, `cli_schedule.py`, the schedule API files, `scheduling_support.py` and `schedule_api_support.py`, the new hooks, `components/schedules/`, `mock-data/contacts.json`.
- README "Security notes": a "Scheduled analysis and email" bullet; "Known limits" now mentions schedules.
- `CLAUDE.md` "Delivery" line: Mailpit.
- `docs/SECURITY_GUARDRAILS.md`: a threat-model row for scheduled-run emails; Mailpit in section 6 (Deployment).
- `.claude/rules/llm-and-security.md`: the facts-only email rule, with `notify/**` and `scheduling/**` added to its paths so it loads for those files.
- `.claude/commands/demo.md`: a scheduling drill step.

Not changed: `docs/DR_Readiness_Agent.pptx` (the deck does not cover scheduling yet; a slide can be added on request).

## Notes
- This checkout uses `core.autocrlf=true`, so git's "CRLF will be replaced by LF" warnings on changed files are expected. The Phase 16 conversion of 27 files to LF was unnecessary but harmless (git stores LF either way); the memory note was corrected.
- A script edit in `api/deps.py` silently matched nothing on a CRLF file; it was caught by `mypy` and redone with the Edit tool.

## Next
The scheduled-analysis feature (Phases 15-17) is complete. The remaining step is the Docker run: `SCHEDULER_ENABLED=true docker compose up --build`, then check the inbox at http://localhost:8025. Beyond the PoC, see design section 14 (directory adapters, a real mail relay, several API instances, authentication).
