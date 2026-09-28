# Design: scheduled readiness analysis with email notification

| | |
|---|---|
| Status | Accepted 2026-09-26 (Phase 15 reviewed by the project owner) |
| Date | 2026-09-26 |
| Phases | 15 (this document, done), 16 (scheduler and notification core, done, see section 16), 17 (API, UI, CLI and delivery, done, see section 17), 18 (monthly schedules, saved runbook uploads, browser timezone, one date-time format, done, see section 18), see [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) |
| Decisions | [0010](../adr/0010-in-process-scheduler.md), [0011](../adr/0011-recipients-and-email-content.md) |

## 1. Context

An analysis runs only when someone starts it from the CLI, the API or the dashboard. DR readiness decays between those moments: dependencies change, owners move and runbooks drift. Nobody finds out until the next manual check or an incident.

Decisions made with the project owner on 2026-09-26:

- Users **schedule** analyses of a DR runbook. The system runs them on time and **emails the responsible person** a summary after every run.
- The scheduler **only analyzes, it never executes**. The UI lists schedules and their runs. From a run, a person starts an execution (dry run or live) with the existing approval-gated flow.
- Schedules use **presets** (hourly, daily at HH:MM, weekly on a day at HH:MM) in a chosen timezone, not cron expressions.
- The runbook and inventory come from **server paths under `API_ALLOWED_DIR`** and are **re-read on every run**, so edits are picked up.
- Email goes over **SMTP**. The PoC ships **Mailpit** as a local inbox. In the PoC the recipient is configurable. In production the **owner named in the runbook** is looked up in a directory tool.
- Users can **pause, resume, pause until a date, pause all and cancel a running run**.

What already exists and is reused unchanged:

- `JobStore` (`api/jobs.py`) runs analyses as background jobs with a concurrency cap and hands every finished job to `history_saver()` (`api/analysis_lookup.py`), which stores it (ADR 0007).
- `finished_analysis()` (`api/analysis_lookup.py`) finds an analysis in memory **or in the history**, and `POST /api/v1/executions {analysisJobId}` creates an execution from it. A scheduled run's analysis can therefore be executed with no new execution code. That keeps the rule "execution always follows an analysis" and adds no new execution entry point.

## 2. Goals and non-goals

**Goals**
- Create, edit, pause, resume and delete schedules from the API and the UI; list them from the CLI.
- Run each due schedule once per slot, save the analysis as a normal stored analysis (`source = scheduled`) and email a summary.
- Show every run with its result and email status, and let a person open the report and start an execution from it.
- Resolve the recipient from configuration in the PoC, through a `ContactDirectory` interface that a real directory can implement later.

**Non-goals**
- Starting executions from the scheduler, or any automatic execution.
- Cron expressions, calendars, holidays or maintenance windows other than "pause until".
- Several API instances (section 14). The PoC runs one scheduler in one API process.
- Authentication. As with approvers, "created by" and "paused by" names are self-declared until the API has login (section 13).
- Other channels (Slack, Teams, pager). The `Notifier` interface leaves room for them.

## 3. Architecture

```
API process (lifespan)
 ├─ Scheduler (scheduling/runner.py) ── tick every SCHEDULER_TICK_SECONDS
 │    ├─ ScheduleStore (SQLite, same DB_PATH)  claim_due(now)
 │    ├─ analyze callable ──► JobStore.submit ──► analyze_runbook() ──► history_saver() (source=scheduled)
 │    ├─ ContactDirectory (notify/directory.py)  owner name ─► email
 │    └─ Notifier (notify/smtp.py)  ─► SMTP (Mailpit in the PoC)
 └─ Existing routes: history, executions (POST /executions {analysisJobId = run.analysisId})
```

- `scheduling/` and `notify/` are framework-free (no FastAPI or Typer imports), like `core/` and `execution/`. Everything they need is injected: clock, store, analyze callable, directory, notifier.
- `scheduling/` never imports `execution/`. A test checks the import graph and that a scheduled run creates no execution.
- The scheduler starts and stops in the `api/app.py` lifespan, next to the execution service, and only when `SCHEDULER_ENABLED=true`. It needs the history (`HISTORY_ENABLED=true`), otherwise startup fails with a `ConfigError`. Without stored analyses a run could not be executed after a restart.
- The CLI does not run the scheduler. It reads schedules and runs from the same database.

## 4. Data model (migration 3)

### 4.1 `schedules`
| Column | Notes |
|---|---|
| `id` TEXT PK | Same id format as analyses (`^[A-Za-z0-9_-]{1,64}$`) |
| `name` TEXT | 1-100 chars |
| `runbook_path`, `inventory_path` TEXT | Relative to `API_ALLOWED_DIR`; inventory optional |
| `cadence_json` TEXT | `{"kind":"hourly","minute":15}`, `{"kind":"daily","time":"06:00"}`, `{"kind":"weekly","weekday":"mon","time":"06:00"}` |
| `timezone` TEXT | IANA name, e.g. `Europe/Berlin`; default `SCHEDULER_DEFAULT_TIMEZONE` (`UTC`) |
| `recipients_json` TEXT NULL | Optional override, 1-5 addresses |
| `enabled` INTEGER | 0 = paused |
| `pause_until` TEXT NULL | UTC; paused until then, then resumes by itself |
| `paused_by`, `paused_at` | Who paused and when (self-declared name) |
| `created_by`, `created_at`, `updated_at` | |
| `next_run_at` TEXT NULL | UTC; NULL while paused |
| `last_run_at` TEXT NULL | |

Index: `schedules_due (enabled, next_run_at)`.

### 4.2 `schedule_runs`
| Column | Notes |
|---|---|
| `id` TEXT PK | |
| `schedule_id` TEXT | `REFERENCES schedules(id) ON DELETE CASCADE` |
| `slot_at` TEXT | The planned time this run belongs to; `run-now` uses the request time |
| `trigger` TEXT | `scheduled` or `manual` (run now) |
| `state` TEXT | `running`, `succeeded`, `failed`, `cancelled` |
| `started_at`, `finished_at` TEXT | |
| `analysis_id` TEXT NULL | `REFERENCES analyses(id) ON DELETE SET NULL` |
| `job_id` TEXT NULL | The analysis job, kept even when the history could not store it (then `analysis_id` stays NULL and the run cannot be executed after a restart) |
| `risk_score`, `risk_level`, `rto_feasible` | Copied from the report for the run list |
| `email_state` TEXT | `sent`, `failed`, `skipped` |
| `email_to` TEXT NULL | Resolved recipients, comma-separated |
| `error_code`, `error` TEXT NULL | Short, never runbook text |

Index: `schedule_runs_by_schedule (schedule_id, started_at)`. A unique index on `(schedule_id, slot_at, trigger)` makes a double run of the same slot impossible.

### 4.3 `scheduler_state`
A single row: `paused` (0/1), `pause_until`, `paused_by`, `paused_at`. It survives restarts.

### 4.4 Other changes
- `AnalysisSource.SCHEDULED` in `history/models.py`; `Job` gets `source` so `history_saver()` records it. The History tab can filter by source.
- Deleting an analysis still returns `409` while executions refer to it. A schedule run pointing to it only loses its link (`ON DELETE SET NULL`); the run list then shows "report no longer stored".
- Deleting a schedule deletes its runs. The analyses stay in the history.

## 5. Scheduling rules

### 5.1 Presets and next run
`next_run_after(cadence, timezone, after) -> datetime` is a pure function (`scheduling/next_run.py`). It returns the first slot strictly after `after`, in UTC:
- `hourly{minute 0-59}`: the next hh:minute.
- `daily{time HH:MM}`: today or tomorrow at that local time.
- `weekly{weekday, time}`: the next such weekday at that local time.

Timezones use `zoneinfo` with the `tzdata` package (Windows has no system tz database). DST rules:
- A local time that does not exist (spring forward) moves to the first valid minute after it.
- A local time that occurs twice (fall back) runs once, at the first occurrence.

### 5.2 Claiming due schedules
Every tick (`SCHEDULER_TICK_SECONDS`, default 30), `claim_due(now)` selects enabled schedules with `next_run_at <= now` that are not paused (no global pause, `pause_until` passed or empty). In one transaction (`BEGIN IMMEDIATE`) it inserts the run (unique per slot) and moves `next_run_at` to the next slot after `now`. A slot can therefore never run twice, even if two ticks overlap.

### 5.3 Missed slots
If the API was down, a schedule whose `next_run_at` is in the past runs **once** at startup, then continues from the next future slot. Missed slots are not replayed, so a long outage never causes a burst of analyses and emails.

### 5.4 Run flow
1. Resolve `runbook_path` (and `inventory_path`) with `resolve_allowed_path()` and read them with `loaders.py`. A path that has become invalid fails the run with `PATH_NOT_ALLOWED` or `NOT_FOUND`.
2. Parse with `service.parse_markdown()`. A parse error fails the run with `PARSE_ERROR`.
3. Submit through the injected analyze callable. The API wires it to `JobStore.submit(..., source=scheduled)`, so scheduled runs share the concurrency cap, the knowledge base and history saving with interactive analyses. The job id is the run's `analysis_id`.
4. Wait for the job. On success, copy risk, level and RTO verdict to the run. If the store is full (`CapacityError`), the run fails with `CAPACITY_EXCEEDED` and waits for the next slot.
5. Resolve the recipients (section 7) and send the email (section 8). An email failure sets `email_state = failed` and is logged, but never fails the run. The same rule applies to history saving.
6. A failed run also sends a short failure email, so a broken schedule does not go unnoticed.

### 5.5 Run now
`POST /schedules/{id}/run-now` creates a `manual` run for the current time. It does not move `next_run_at`, works while the schedule is paused (an explicit user action) and is refused while a run of the same schedule is still `running` (`409`).

## 6. Stopping and pausing

| Action | Effect | Resumes |
|---|---|---|
| Pause a schedule | `enabled = 0`, `next_run_at = NULL`, paused by/at recorded | Manual resume |
| Pause a schedule until a date | As above, with `pause_until` | Automatically at `pause_until`, or manual resume |
| Pause all | `scheduler_state.paused = 1`; no schedule is claimed | Manual resume all |
| Pause all until a date | As above, with `pause_until` | Automatically, or manual resume all |
| Cancel a running run | The analysis job is cancelled; run `cancelled`; **no email** | Not applicable |
| Delete a schedule | Schedule and its runs removed; a running run is cancelled first | Not applicable |
| Operator kill switch | `SCHEDULER_ENABLED=false` and restart; all schedule endpoints return `403 SCHEDULER_DISABLED` | Config change and restart |

- `pause_until` must be in the future and at most `SCHEDULER_MAX_PAUSE_DAYS` (default 90) ahead. A manual resume clears it.
- **Resume rule:** on any resume (manual or `pause_until` reached), `next_run_at = next_run_after(cadence, tz, now)`. Missed slots are skipped.
- Pausing never stops a run that has already started. Cancel does that. `JobStore` gains `cancel(job_id)` for it.
- Every pause, resume and cancel is logged with the name given (self-declared, section 13).

## 7. Recipients

`notify/recipients.py` resolves, in order:
1. The schedule's **recipient override**, if set (PoC convenience).
2. **Directory lookup** of the runbook owner (`runbook.system_owner`, from `**Owner:**`) through `ContactDirectory.email_for(name)`.
3. `NOTIFY_DEFAULT_EMAIL`.

If none applies, `email_state = skipped` with the reason "no recipient", and the run is still saved.

- The owner text comes from the runbook, so it is **untrusted**. It is used **only as a lookup key**, never as an address, even if it looks like one. "Unspecified", "team" and empty owners (already flagged by the parser) fall through to the default. The email then says the runbook has no resolvable owner.
- Every address, from override, directory or default, must match a simple address pattern and a domain in `NOTIFY_ALLOWED_DOMAINS`. Other addresses are dropped and logged. Without an allow-list the API could be used to send mail to arbitrary addresses.
- PoC directory: `StaticContactDirectory` reads `NOTIFY_CONTACTS_FILE` (JSON `{"Alice Chen": "alice.chen@example.com", ...}`, names case-insensitive). The bundled `mock-data/contacts.json` uses `example.com` addresses only (reserved by RFC 2606).
- Production: another `ContactDirectory` implementation, chosen by `NOTIFY_DIRECTORY` in `wiring.py` (section 14). Step owners could be added as CC later.

## 8. Email content

Built with `email.message.EmailMessage` (`notify/message.py`), which rejects CR/LF in headers. The subject also has control characters stripped and is limited to 150 characters:

`[DR readiness] estimate-service: HIGH risk (72/100), RTO at risk`

Body, as plain text plus an autoescaped Jinja2 HTML part (same approach as `formatters/format_html.py`), with **facts computed by code only**:
- Service (reduced to a plain identifier: letters, digits, `.`, `_`, `-`), schedule name and cadence, run time (in the schedule's timezone), and the owner's name **only when the directory matched it**; otherwise "not found in the directory". (Changed in Phase 16: an unmatched owner line is runbook text and stays out.)
- Risk score and level, RTO feasible or not, estimated time vs RTO and the buffer.
- Number of gaps by severity, number of single points of failure, dependency health counts (up, down, unreachable, not in inventory).
- Whether AI analysis was available.
- A link to the run: `UI_BASE_URL/#/schedules/{scheduleId}/runs/{runId}` (left out when `UI_BASE_URL` is empty).
- For a failed run: the error code and a one-line reason.

It deliberately contains **no runbook text and no LLM text** (summary, reasoning, gap descriptions). Runbook content is untrusted, and an injected runbook must not be able to put convincing phishing text into an email sent by the organisation's own system. Readers follow the link for details.

`SmtpNotifier` (`notify/smtp.py`) uses stdlib `smtplib` in `asyncio.to_thread`, with optional STARTTLS and login. `SMTP_PASSWORD` is a `SecretStr` and is covered by the existing log redaction. There is one attempt per run with a timeout, and no retry loop. `LogNotifier` (`NOTIFY_TRANSPORT=log`) logs the recipients and subject instead of sending, for tests and machines without SMTP.

## 9. HTTP API (Phase 17)

All endpoints return `403 SCHEDULER_DISABLED` when the scheduler is off.

| Method and path | Purpose |
|---|---|
| `GET /api/v1/schedules` | List, with the last run's state and risk |
| `POST /api/v1/schedules` | Create (`name`, `runbookPath`, `inventoryPath?`, `cadence`, `timezone`, `recipients?`, `createdBy`); paths checked with `resolve_allowed_path()`; `409` above `SCHEDULER_MAX_SCHEDULES` |
| `GET/PUT/DELETE /api/v1/schedules/{id}` | Read, update (including `enabled`, `pauseUntil`, `pausedBy`), delete |
| `POST /api/v1/schedules/{id}/run-now` | Start a manual run; returns the run |
| `GET /api/v1/schedules/{id}/runs` | Runs, newest first, keyset pages as in the history API |
| `GET /api/v1/schedule-runs/{runId}` | One run, with `jobId` and `analysisId` (set only when the analysis is stored) |
| `POST /api/v1/schedule-runs/{runId}/cancel` | Cancel a running run (`409` if not running) |
| `GET /api/v1/scheduler` | Global state (paused, pause until, by, at) and settings (tick, limits, email transport, whether a default recipient is set) |
| `POST /api/v1/scheduler/pause` `{until?, by}`, `POST /api/v1/scheduler/resume` `{by}` | Pause and resume all |
| `GET /api/v1/schedules/recipient-preview?runbookPath=` | The resolved recipient for the form |

Executing uses the **existing** `POST /api/v1/executions {analysisJobId: run.analysisId}`. `poe gen-api` refreshes the typed client.

## 10. CLI (Phase 17)

`dr-agent schedule list` and `dr-agent schedule runs ID` (`cli_schedule.py`) read the database and print tables. Changing schedules stays in the API and UI for the PoC, because the scheduler lives in the API process and must see changes at once. `dr-agent execute --analysis <run's analysisId>` already executes a scheduled run's analysis.

## 11. User interface (Phase 17)

A new **Schedules** tab (`components/schedules/`, `api/scheduleClient.ts`, hooks):
- **List:** name, runbook, cadence in words ("Daily 06:00 Europe/Berlin"), next run, last result (risk badge, RTO verdict, email status), state ("Active", "Paused by Alice", "Paused until 28 Sep 06:00"), actions: run now, pause or resume, pause until, edit, delete.
- **Pause all** toggle with an optional date, and a banner while the whole scheduler is paused.
- **Form:** name, runbook and inventory from the sample list (`routes_samples.py`), cadence preset, timezone (the browser's by default), optional recipients, and "Email goes to: …" from the preview endpoint.
- **Runs:** time, trigger, state, risk, RTO, email status, cancel while running.
- **Run detail:** the stored report in the existing `ReportView`, and under it the existing `ExecutionSection` with `analysisJobId = analysisId`. Dry runs, live runs, approvals and the "Create live run" rule work exactly as for an interactive analysis. The History tab stays read-only (Post-Phase-14 decision).
- The app has no router today. A small hash reader (`#/schedules/{id}/runs/{runId}`) opens the Schedules tab on a run so that email links work, with no router dependency.

## 12. Configuration

| Setting | Default | Notes |
|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Off by default, like execution |
| `SCHEDULER_TICK_SECONDS` | `30` | |
| `SCHEDULER_MAX_SCHEDULES` | `50` | |
| `SCHEDULER_MAX_PAUSE_DAYS` | `90` | |
| `SCHEDULER_DEFAULT_TIMEZONE` | `UTC` | |
| `NOTIFY_TRANSPORT` | `log` | `smtp` or `log` |
| `SMTP_HOST`, `SMTP_PORT` | `localhost`, `1025` | Mailpit in Compose |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | empty | Password is a `SecretStr` |
| `SMTP_STARTTLS` | `false` | Must be `true` for a real relay |
| `SMTP_TIMEOUT_SECONDS` | `10` | |
| `NOTIFY_FROM` | `dr-agent@example.com` | |
| `NOTIFY_DEFAULT_EMAIL` | empty | |
| `NOTIFY_ALLOWED_DOMAINS` | `example.com` | Comma-separated |
| `NOTIFY_DIRECTORY` | `static` | Future: `ldap`, `graph`, `pagerduty`, ... |
| `NOTIFY_CONTACTS_FILE` | empty | JSON name to email |
| `UI_BASE_URL` | empty | For links in emails |

New dependency: `tzdata` (Apache-2.0). Dev only: `aiosmtpd` (Apache-2.0) for the SMTP integration test. Compose adds `axllent/mailpit` (MIT).

## 13. Security notes

- **No execution from the scheduler.** It is enforced by the import boundary, a test, and by using the existing, approval-gated execution endpoint for anything that runs.
- **Untrusted runbook text** never reaches an email. The owner name is only a lookup key, and emails carry code-computed facts only (section 8).
- **No open mail relay.** Recipients are limited to `NOTIFY_ALLOWED_DOMAINS` and at most 5 per schedule, and the number of schedules and the finest cadence (hourly) cap the volume.
- **Header injection.** `EmailMessage` rejects CR/LF in headers; the subject is also sanitized.
- **Paths.** Runbook and inventory paths go through the same allow-list as `GET /analyze`, checked both when saved and on every run.
- **Secrets.** `SMTP_PASSWORD` is a `SecretStr`, redacted in logs, and never returned by the API (`GET /scheduler` only says whether SMTP login is configured).
- **Identity.** "Created by" and "paused by" are self-declared names, like approvers today. Until the API has authentication, anyone who can reach it can pause or change schedules. This is listed with the other PoC gaps in `docs/SECURITY_GUARDRAILS.md`.
- **Containers.** Mailpit runs on the internal network. Only its web inbox is published, on `127.0.0.1:8025`, for the demo.

## 14. Production path and later work

- **Directory adapters** behind `ContactDirectory`: LDAP, Entra ID (Microsoft Graph) or Okta to map a person's name to an address; PagerDuty or Opsgenie to email whoever is on call for the service; ServiceNow CMDB to look up the service owner by service name instead of the runbook text. A lookup cache with a short TTL and a fallback to `NOTIFY_DEFAULT_EMAIL` when the directory is down.
- **Mail:** a real SMTP relay with STARTTLS, or a provider API (SES, SendGrid) as another `Notifier`. SPF/DKIM for the sender domain.
- **More than one API instance:** `claim_due` needs a shared database (Postgres, which the store protocols already allow) and a lock (e.g. a Postgres advisory lock) or a separate scheduler worker process.
- **Authentication:** schedule and pause actions tied to logged-in users; only owners or admins may change a schedule.
- **Other channels** (Slack, Teams) as further `Notifier` implementations; emailing only when something changed as a per-schedule option.

## 15. Testing strategy

- **Unit (Phase 16):**
  - `next_run_after` for every preset, month and year boundaries, DST gaps and overlaps in `Europe/Berlin` and `America/New_York`, and `UTC`.
  - The store: claim once per slot, global pause, `pause_until`, and resume skipping missed slots.
  - The scheduler with a fake clock, fake analyze and `LogNotifier`:
    - due claiming and the missed-slot-once rule
    - run now
    - analysis failure, parse failure and `CAPACITY_EXCEEDED`
    - an email failure does not fail the run
    - cancel sends no email
    - **no execution is created**
  - Recipient order, untrusted owner names, the domain allow-list, and the message builder (no runbook or LLM text, header injection).
  - Migration 3 from a version-2 database; pause state surviving a restart.
- **Integration (Phase 17):**
  - API with a fake LLM: create, run now, analysis stored with `source=scheduled`, email captured by `aiosmtpd`, dry run created from `analysisId`.
  - `403` when disabled, path traversal rejected, pause, pause until, pause all, and cancel through the API.
- **UI (Phase 17):** vitest for the list, form, runs, run detail (execution section bound to the run's analysis) and the hash link.
- **End to end (Phase 17):** browser drill with Mailpit:
  1. Create an hourly schedule for `runbooks/estimate-service-executable.md`.
  2. Run it now.
  3. Check the email for Alice Chen in Mailpit.
  4. Follow the link and create a dry run.
  5. Pause until tomorrow, then pause all.

## 16. Implementation notes (Phase 16)

Built on 2026-09-27 as designed, with these details and differences:

- **Packages.** `scheduling/`: `models.py`, `next_run.py`, `store.py` (protocol), `sqlite_store.py` + `sqlite_rows.py` + `sqlite_claim.py`, `source.py` (`AllowedDirSource` reuses `api/paths.py` `resolve_allowed_path()`, which is framework-free), `emailing.py` (`RunEmailer`), `runner.py` (`Scheduler`), `service.py` (`ScheduleService`). `notify/`: `directory.py`, `recipients.py`, `facts.py`, `message.py` (+ `templates/scheduled_run_email.html.jinja`), `senders.py`. Neither package imports `execution/` or FastAPI (test-enforced).
- **Runs table.** `job_id` (always) plus `analysis_id` (foreign key, only for a stored analysis) instead of an `analysis_stored` flag, because the foreign key cannot point at an analysis the history failed to save.
- **Owner in emails.** Shown only when the contact directory matched it (section 8). An unmatched owner line is runbook text.
- **Overlapping runs.** A slot that comes due while the previous run of the same schedule is still going is skipped (logged as `schedule_slot_skipped`), and so is a slot that already has a run recorded.
- **Stopping.** Cancelling a run cancels the analysis through the injected analyze callable, stores `cancelled` and sends no email. At shutdown a running run is stored as `failed` / `INTERRUPTED`. `recover()` at startup marks runs left `running` the same way. `JobStore.cancel(job_id)` added; its cancelled-job message now reads "job cancelled (by a user or at shutdown)".
- **Errors.** New `SchedulerDisabledError` (`SCHEDULER_DISABLED`, 403) and `NotificationError` (`NOTIFICATION_FAILED`, 502). The capacity failure code is `CAPACITY_EXCEEDED` (the existing `CapacityError` code). A duplicate manual run at the same instant is a `ConflictError`.
- **Config.** Validated at startup: `SCHEDULER_ENABLED` needs `HISTORY_ENABLED`; timezone, sender and default addresses, and `UI_BASE_URL` (http(s) only) are checked; blank optional values count as unset. `wiring.py` gains `build_notifier()`, `build_directory()` and `email_settings()`. `mock-data/contacts.json` holds `example.com` addresses for every runbook owner.
- **Not yet wired.** The API lifespan, routes, UI, CLI and Compose (Mailpit) are Phase 17. The analyze callable that submits to `JobStore` (with `source=scheduled`) and cancels the job when its task is cancelled is part of that wiring.

## 17. Implementation notes (Phase 17)

Built on 2026-09-27 as designed, with these details and differences:

- **Wiring.** `scheduling_runtime.py` builds the scheduler from settings (like `execution_runtime.py`); `api/scheduled_jobs.py` is the analyze callable: a normal `JobStore` job with `source=scheduled`, and cancelling the waiting task cancels the job. The API lifespan opens it when `SCHEDULER_ENABLED=true`, starts the ticker, and stops it **before** the job store at shutdown, so a running run ends as `INTERRUPTED` instead of failing with a cancelled job and sending a failure email. `create_app()` takes an optional `notifier` (tests capture emails with it).
- **API.** `api/routes_schedules.py` and `api/routes_scheduler.py`, schemas in `api/schemas_schedules.py`. Differences from section 9: pausing and resuming one schedule are `POST /schedules/{id}/pause {by, until?}` and `/resume {by}` rather than fields of `PUT` (a pause needs a name and its own validation, and `PUT` stays a plain replace of the settings); the recipient preview is `GET /scheduler/recipient-preview`, because `/schedules/recipient-preview` would be taken by `/schedules/{id}`. `ScheduleView` adds `description` (cadence in words) and `lastRun`; `SchedulerView` adds the limits and whether a default recipient is set, never SMTP details. A missing `timezone` on create takes `SCHEDULER_DEFAULT_TIMEZONE`.
- **CLI.** `cli_schedule.py`: `dr-agent schedule list` and `schedule runs ID`, read-only, straight from the database (they also work while the scheduler is off, and say so).
- **UI.** `components/schedules/` (`SchedulesView`, `ScheduleList`, `ScheduleForm`, `CadenceFields`, `RecipientLine`, `PauseForm`, `SchedulerBar`, `ScheduleRuns`, `ScheduledRunDetail`, `YourName`), `api/scheduleClient.ts`, `hooks/useSchedules.ts`, `hooks/useScheduleRuns.ts` (polls while a run is going), `lib/scheduleLabels.ts`. A run's detail shows the stored report and the existing `ExecuteRunbook` / `ExecutionSection` with `jobId = analysisId`; this is the second place (after a fresh report) where an execution can start, and the frontend rule was updated accordingly. The History tab stays read-only. The email-link hash is read on load **and** on `hashchange` (found in the browser drill: a link opened in an already open tab did nothing), and "Back to schedules" clears it so a reload shows the list.
- **Delivery.** Compose adds `axllent/mailpit:v1.31.3` with the shared hardening, on a new internal `mail` network with `api` (SMTP) plus the default network only to publish the web inbox on `127.0.0.1:8025`; `api` gets the scheduler and notify settings with `NOTIFY_TRANSPORT=smtp`. Docker is not installed on the development machine, so the compose change is validated by YAML parsing here and by the CI `docker` job.
- **Browser drill (2026-09-27).** Run against `uv run poe dev-api` (scheduler, execution and SMTP on, rules only) with an `aiosmtpd` catcher standing in for Mailpit: create an hourly schedule, run now, email to Alice Chen with facts only and a working link, open the report from the run and from the link, create a dry run from it, pause until a date, pause all, resume both. Two issues found and fixed (hash change in an open tab; the linked run showed "this schedule" instead of its name), plus the create form now clears after success. Steps and screenshots in `scratchpad/phase-17/`.

## 18. Phase 18 additions (owner requests, 2026-09-27)

### 18.1 Monthly cadence
`MonthlyCadence {kind: "monthly", day: 1-31 | "last", time: "HH:MM"}` joins the presets. A day the month does not have runs on that month's last day, so day 31 runs on 30 April and on 28 or 29 February, and no month is skipped. `"last"` always means the last day. Slots are computed like the other presets: local wall-clock candidates, month by month (up to 14 ahead), converted with the same DST rules (section 5.1). Stored in `cadence_json`, so no migration.

### 18.2 Saved runbook uploads
`POST /api/v1/dr/samples/runbooks` (multipart `file`, or JSON `{fileName, markdown}`) saves a runbook under `API_ALLOWED_DIR/<RUNBOOK_UPLOAD_DIR>` (default `uploads`), so schedules, `GET /analyze` and the Analyze tab can use it through the existing allow-list. Before anything is written: the size limit (`API_MAX_UPLOAD_BYTES`), a `.md` / `.markdown` name, UTF-8, and a successful parse (`422 PARSE_ERROR` otherwise), so a schedule never points at a file that cannot run. The stored name is reduced to `[a-z0-9-]` plus `.md`; an existing name gets `-2`, `-3`, … and nothing is ever overwritten; the file is written to a temporary name in the same folder and renamed. `RUNBOOK_UPLOAD_MAX_FILES` (default 200) caps the folder (`409`), and `RUNBOOK_UPLOADS_ENABLED=false` turns uploads off (`403 UPLOADS_DISABLED`). Runbooks only; inventories keep coming from the sample folder. In Compose the image stays read-only and a named volume `dr-agent-uploads` is mounted at `/app/mock-data/uploads`.

### 18.3 Timezone from the browser
The schedule form no longer has a timezone field: the browser's zone (`Intl.DateTimeFormat().resolvedOptions().timeZone`) is shown read-only and sent with the schedule, falling back to `UTC` (and saying so) when the browser reports none. Editing keeps the stored zone. The API still validates the name and still applies `SCHEDULER_DEFAULT_TIMEZONE` when a client sends none.

### 18.4 One date-time rule
Stored and exchanged in UTC (database, API, JSON reports); shown to people in their local time in one format, `28 Sep 2026, 11:30 UTC+05:30` (seconds where they matter; a zero offset shows `UTC`). The numeric offset is used because browsers and Python name zones differently. Whose local time: the browser's in every dashboard view, the machine's in the CLI, the downloading browser's in the HTML export (`?tz=`, UTC without it), the schedule's in emails (the server cannot know each recipient's). One formatter per side (`formatDateTime()` in the frontend, `utils/timefmt.py` `display_time()` in the backend), tested on the same cases.

### 18.5 Security notes
Uploads are the first feature that writes user content to disk. The controls above keep writes inside one folder, bounded in size and count, never overwriting, and parse-checked; the content is untrusted like any runbook (delimited in prompts, never logged, served only as text). Without authentication anyone who can reach the API can upload, which is listed with the other PoC gaps.

### 18.6 Implementation notes (Phase 18)

Built on 2026-09-27 as described above, with these details:

- **Files.** `scheduling/models.py` (`MonthlyCadence`) and `next_run.py` (`_monthly()`, `describe()`); `runbook_uploads.py` (`RunbookUploads`, `safe_stem()`: exclusive create reserves the name, a temporary file is moved over it); `api/body_upload.py` (JSON or multipart reader; `UploadRunbookRequest` keeps the text exactly, without the base model's whitespace stripping) and `POST /runbooks` in `api/routes_samples.py`, documented in OpenAPI through `UPLOAD_REQUEST_BODY`; `utils/timefmt.py` (`display_time()`, `zone_or_none()`) used by the CLI, emails and the HTML export (`?tz=` on both report routes); frontend `formatDateTime()` and `browserTimezone()` in `lib/labels.ts`, `RunbookPicker`, monthly fields in `CadenceFields`, the read-only timezone line in `ScheduleForm`, `uploadRunbook()` and `tzQuery()` in the API client.
- **Added while building.** `DISPLAY_TIMEZONE` (CLI only): the CLI uses the machine's zone by default, and on Windows the `TZ` variable has no effect, so tests (and users) need a setting. `config_extras.py` holds the notify, SMTP, display and upload settings and `Settings` inherits them, keeping `config.py` under 200 lines; variable names are unchanged. `UploadsDisabledError` (`UPLOADS_DISABLED`, 403). The Docker image creates `/app/mock-data/uploads` owned by the app user, because a new named volume copies the ownership of the path it is mounted on. `mock-data/uploads/` is git- and docker-ignored.
- **Known quirk kept.** `GET /api/v1/dr/samples/file` returns every sample's text trimmed of surrounding whitespace (the base model strips strings); the saved file itself is exact. Not changed in this phase.
