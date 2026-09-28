# Phase 16 summary: scheduler and notification core

Date: 2026-09-27. Status: done. Exit criteria met. Not committed (owner asked for no commits).

## Before starting
- Owner approved the design and ADRs 0010-0011 on 2026-09-26; both set to Accepted, design status Accepted, plan and README updated.
- Re-verified Phases 0-15: lint clean (ruff, 242 files formatted, `mypy --strict` 139 files, eslint/tsc/prettier), 1005 backend tests at 98.89%, 114 UI tests (97.25% lines).

## What was built
| Area | Files |
|---|---|
| Models and slots | `scheduling/models.py` (cadence presets, `Schedule`, `ScheduleRun`, `SchedulerState`, `is_email`), `scheduling/next_run.py` (`next_run_after`, DST-safe, `describe`) |
| Storage | migration 3 in `storage/migrations.py` (`schedules`, `schedule_runs`, `scheduler_state`); `scheduling/store.py` (protocol), `sqlite_store.py`, `sqlite_rows.py`, `sqlite_claim.py` |
| Running | `scheduling/source.py` (`AllowedDirSource`), `scheduling/runner.py` (`Scheduler`: tick, run now, cancel, recover, shutdown), `scheduling/emailing.py` (`RunEmailer`), `scheduling/service.py` (`ScheduleService`: create, update, delete, pause, pause until, resume, pause all, resume all) |
| Email | `notify/directory.py` (`ContactDirectory`, static JSON, empty), `notify/recipients.py`, `notify/facts.py`, `notify/message.py` + `templates/scheduled_run_email.html.jinja`, `notify/senders.py` (`SmtpNotifier`, `LogNotifier`) |
| Changes to existing code | `AnalysisSource.SCHEDULED`; `Job.source` and `JobStore.submit(source=...)`, `JobStore.cancel()`; `history_saver()` stores `job.source`; `SchedulerDisabledError` (403), `NotificationError` (502) mapped in `api/errors.py`; `config.py` scheduler and notify settings; `wiring.py` `build_notifier()`, `build_directory()`, `email_settings()` |
| Data and config | `mock-data/contacts.json` (`example.com` addresses for every runbook owner), `.env.example` block; dependencies `tzdata` (runtime), `aiosmtpd` (dev) via `uv add` |
| Generated | `uv run poe gen-api`: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (`"scheduled"` added to the analysis source enum) |
| Docs | design section 16 plus fixes in sections 4.2, 5.4, 8, 9 and 15; `docs/IMPLEMENTATION_PLAN.md`; README (layout, configuration, "Email and contact lookup", roadmap); `docs/SECURITY_GUARDRAILS.md` new section 7 and a gap row; `CLAUDE.md`; `.claude/rules/python-backend.md`, `testing.md`; phase-workflow skill |

## Tests (118 new backend tests)
- `test_scheduling_next_run.py`: all presets, month and year boundaries, DST spring-forward gap (Berlin and New York) and fall-back overlap (runs once), strictly-after rule.
- `test_scheduling_models.py`: cadence, timezone and recipient validation, `is_email` (header-injection attempts rejected).
- `test_scheduling_store.py`, `test_scheduling_pause.py`: round trip, claim once per slot, missed slots run once, running run skips a slot, already-recorded slot skipped, a failing claim changes nothing, manual runs and conflicts, run pages, interrupted runs after a restart, cascade delete, analysis deletion keeps the run (`ON DELETE SET NULL`), pause until auto-resume, global pause and its expiry, resume all.
- `test_scheduling_runner.py`: success (stored, emailed to the owner from the directory, link, facts), no runbook, summary, gap or suggestion text in the email, unstored analysis note, capacity failure email, parse failure mailed to the default, missing file, crash, email failure does not fail the run, nobody to mail.
- `test_scheduling_control.py`: cancel (no email, analysis cancelled), orphan cancel, shutdown interrupts and `recover()`, delete cancels a running run, the ticker survives a failing tick, **no execution created** and no `execution` or FastAPI import in `scheduling/` or `notify/`.
- `test_scheduling_service.py`: first slot, path allow-list at save time, limits and names, update, pause and resume skipping missed slots, pause-until limits, pause all, run now while paused and conflicts.
- `test_notify_recipients.py`, `test_notify_message.py`, `test_notify_senders.py`: resolution order, untrusted owners (including an address in the owner line), domain allow-list, directory outage; subject and header safety, escaped HTML, failure text; SMTP branches with a fake client plus one real SMTP exchange with `aiosmtpd` on 127.0.0.1.
- `test_config_scheduler.py`, and additions to `test_jobs.py`, `test_wiring.py`, `test_storage_migrations.py` (version 2 to 3).

## Gate (final run)
| Check | Result |
|---|---|
| `uv run poe lint` | ruff clean, 272 files formatted, `mypy --strict` no issues in 156 files, eslint/tsc/prettier clean |
| `uv run poe test` | 1123 backend tests passed, coverage 99.01%; 114 UI tests passed, 97.25% lines |
| `uv run poe audit` | `pip-audit`: no known vulnerabilities; `npm audit`: 0 vulnerabilities |
| File sizes | every changed or new file under 200 lines (generated `schema.d.ts` excepted); `test_config.py` and `test_scheduling_store.py` were split (`config_env.py`, `test_scheduling_pause.py`) |
| Warnings | the existing Starlette test-client `DeprecationWarning` only |

## Decisions made while building (open for review)
| # | Decision | Why |
|---|---|---|
| P16-1 | `schedule_runs.job_id` (always) plus `analysis_id` (foreign key, only when stored) instead of an `analysis_stored` flag | A foreign key cannot point at an analysis the history failed to save |
| P16-2 | The email names the owner only when the contact directory matched them | The design listed the owner "as written in the runbook", which is runbook text and contradicts ADR 0011 |
| P16-3 | The service name in emails is reduced to `[A-Za-z0-9._-]` (e.g. `Estimate-Service`) | It comes from the runbook heading; the subject stays safe and plain |
| P16-4 | A slot is skipped when the previous run of that schedule is still going | No overlapping analyses of one runbook; logged as `schedule_slot_skipped` |
| P16-5 | At shutdown a running run is stored as `failed` / `INTERRUPTED`, not `cancelled`; `recover()` does the same for leftovers at startup | "Cancelled" means a person stopped it |
| P16-6 | Capacity failures use the existing `CAPACITY_EXCEEDED` code | Reuse the existing error instead of a new `CAPACITY` code |
| P16-7 | Two manual runs at the same instant give a `ConflictError` | Found by a test: the unique index raised a raw `sqlite3.IntegrityError` |
| P16-8 | `AllowedDirSource` imports `api/paths.py` `resolve_allowed_path()` | It is framework-free (no FastAPI), and one allow-list implementation is safer than two |
| P16-9 | `LogNotifier` keeps only the last 50 messages | It is also the default transport on a long-running server |
| P16-10 | SMTP tests use a fake client for every branch plus one in-process `aiosmtpd` exchange on loopback only | Covers the real protocol without any outside network |

## Issues found and fixed during the phase
- Duplicate manual run at the same timestamp surfaced a raw `sqlite3.IntegrityError` (now `ConflictError`, P16-7).
- A cancel arriving while the email was being sent would have left the run `running`; cancellation is now handled around the whole run.
- Ad-hoc Python edit scripts on Windows wrote CRLF line endings into 27 files; restored to LF before finishing (content unchanged).

## Next
Phase 17 (API, UI tab, CLI, Mailpit in Compose, browser drill) starts only when the owner asks. Its wiring includes the analyze callable that submits to `JobStore` with `source=scheduled` and cancels the job when the run's task is cancelled.
