# Phase 15 summary: scheduled analysis design (documents only)

Date: 2026-09-26. Status: done, awaiting approval by the project owner; ADRs 0010-0011 Proposed.

## Owner decisions (2026-09-26)
- Users schedule readiness analyses of a DR runbook; every run emails a summary to the responsible person.
- The scheduler only analyzes, never executes. The UI lists schedules and runs; a person starts an execution from a run's analysis with the existing approval-gated flow.
- Presets (hourly, daily HH:MM, weekly day + HH:MM) with a timezone, not cron.
- SMTP, with Mailpit as the local inbox in the PoC.
- Email on every run.
- Runbook and inventory from an allow-listed server path, re-read on every run.
- Users can pause, resume, pause until a date, pause all and cancel a running run.
- PoC recipient is configurable; in production the runbook owner's name is looked up in a directory tool.
- Plans go into `docs/IMPLEMENTATION_PLAN.md`; design first, then build.

## Validation of Phases 0-14 (before starting)
| Check | Result |
|---|---|
| `uv run poe lint` | ruff clean, 242 files formatted, `mypy --strict` no issues in 139 files, eslint/tsc/prettier clean |
| `uv run poe test` | 1005 backend tests passed, coverage 98.89%; 114 UI tests passed, 97.25% lines |
| `uv run poe audit` | `pip-audit`: no known vulnerabilities; `npm audit --audit-level=high`: 0 vulnerabilities |
| Warnings | 1 `DeprecationWarning` from inside Starlette's test client (`anyio.abc.BlockingPortal`), not project code |

## Deliverables
- `docs/design/scheduled-analysis.md` (new)
- `docs/adr/0010-in-process-scheduler.md`, `docs/adr/0011-recipients-and-email-content.md` (Proposed); `docs/adr/README.md` index updated
- `docs/IMPLEMENTATION_PLAN.md`: Phase 15 checked off; Phases 16-17 updated with the design additions below
- `README.md` roadmap (Phases 15-17), `CLAUDE.md` designs line, phase list in `.claude/skills/phase-workflow/SKILL.md`

No code changed, so the gate was not rerun after the documents (it was run before, see above).

## Assumptions made in the design (open for review)
| # | Assumption | Why |
|---|---|---|
| P15-1 | Scheduler runs inside the API process, started in the lifespan; off by default (`SCHEDULER_ENABLED=false`) | No new service; same pattern as the execution ticker (ADR 0010) |
| P15-2 | Schedules, runs and global pause state live in the shared SQLite file as migration 3 | One file, real foreign keys to `analyses` |
| P15-3 | Scheduled analyses go through `JobStore` and are stored with `source = scheduled` | Shares the concurrency cap, knowledge base and history; execution works unchanged |
| P15-4 | Scheduler requires `HISTORY_ENABLED=true` (`ConfigError` otherwise) | A run must stay executable after a restart |
| P15-5 | One run per slot, enforced by a unique index and a single claiming transaction | No double analyses or emails |
| P15-6 | A missed slot runs once after downtime; every resume skips missed slots | No bursts after outages or long pauses |
| P15-7 | Full `JobStore` fails the run with `CAPACITY` until the next slot, no queue | Scheduled work must not starve interactive analyses |
| P15-8 | Run now works while a schedule is paused, and is refused (`409`) while a run is active | Explicit user action; no overlapping runs |
| P15-9 | Cancelling a run sends no email; a failed run sends a short failure email | Cancel is deliberate; failures must not go unnoticed |
| P15-10 | `pause_until` at most `SCHEDULER_MAX_PAUSE_DAYS` (90) ahead | Prevents forgotten, effectively permanent pauses |
| P15-11 | Recipient order: schedule override, directory lookup of the runbook owner, `NOTIFY_DEFAULT_EMAIL`; owner text is only a lookup key | Runbook text is untrusted (ADR 0011) |
| P15-12 | Recipients limited to `NOTIFY_ALLOWED_DOMAINS`, max 5 per schedule | The API must not become an open mail relay (added in design) |
| P15-13 | Email carries code-computed facts and a link only; no runbook or LLM text | Keeps injected content out of trusted-looking email (ADR 0011) |
| P15-14 | `NOTIFY_TRANSPORT` defaults to `log`; Compose sets `smtp` with Mailpit | Works on machines without SMTP; real email in the demo |
| P15-15 | Schedule changes only through the API and UI; CLI is read-only | The scheduler lives in the API process and must see changes at once |
| P15-16 | "Created by" and "paused by" are self-declared names | No authentication yet, same as approvers; listed as a PoC gap |
| P15-17 | Small hash reader in the UI for email links, no router dependency | The app switches views with state today |
| P15-18 | New runtime dependency `tzdata`, dev-only `aiosmtpd`, Mailpit image in Compose | All open source (Apache-2.0, Apache-2.0, MIT) |

## Next
Phase 16 (scheduler and notification core) starts only after the owner approves the design and ADRs 0010-0011. On approval, set both ADRs and the design status to Accepted.
