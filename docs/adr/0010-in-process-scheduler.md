# 0010. In-process scheduler with schedules in the shared SQLite file

- Status: Accepted (2026-09-26)
- Date: 2026-09-26
- Related: [design](../design/scheduled-analysis.md) sections 3-6; builds on [ADR 0007](0007-persist-analyses.md) (stored analyses) and the rule that execution always follows an analysis

## Context

The project owner wants readiness analyses to run on a schedule and to email the responsible person after each run. The scheduler must only analyze, never execute. A person starts any execution from a scheduled run's analysis. Something has to decide when a schedule is due, run the analysis, remember what happened, and survive restarts. Users must also be able to pause, resume, pause until a date, pause everything and cancel a run.

## Decision

- Run the scheduler **inside the API process**, as an asyncio task started and stopped in the `api/app.py` lifespan, like the execution ticker. It is off by default (`SCHEDULER_ENABLED=false`) and requires the analysis history.
- Keep schedules, runs and the global pause state in the **same SQLite file** (`DB_PATH`) as analyses and executions, as **migration 3** (`schedules`, `schedule_runs`, `scheduler_state`).
- Submit scheduled analyses through the existing **`JobStore`**, so they share the concurrency cap, the knowledge base and history saving (`source = scheduled`).
- Claim due schedules with a single transaction that inserts the run (unique per schedule and slot) and advances `next_run_at`, so a slot never runs twice.
- Use **presets** (hourly, daily, weekly) in an IANA timezone, computed by a pure `next_run_after()` with `zoneinfo` + `tzdata`, not cron.
- Run a missed slot **once** after downtime and skip the rest. Every resume computes the next slot from now.
- The `scheduling/` package never imports `execution/`. Executing a scheduled run uses the existing `POST /api/v1/executions {analysisJobId}` with the run's stored analysis.

## Consequences

- No new service or process: `docker compose up` and `dr-agent` keep working as before, and schedules survive restarts.
- A scheduled analysis is an ordinary stored analysis, so reports, history, the knowledge base and execution work unchanged.
- Scheduled runs compete with interactive analyses for the same job slots. A full store fails the run with `CAPACITY` until the next slot, rather than queueing without limit.
- Only one API instance may run the scheduler. Scaling out needs a shared database and a lock or a separate worker (design section 14).
- A second migration must be maintained and tested against version-2 databases.
- `tzdata` becomes a runtime dependency (Apache-2.0).

## Alternatives considered

- **APScheduler or Celery beat.** Mature, but they bring their own job stores, persistence and threading models, which would duplicate `JobStore` and the SQLite migrations. Celery also needs a broker.
- **OS cron or Windows Task Scheduler calling the CLI.** Nothing in the product would know about schedules: no UI list, no pause, and no run history linked to analyses.
- **A separate scheduler worker process.** Cleaner for scaling out, but an extra container and process to supervise for a single-instance PoC. The store protocol keeps this possible later.
- **Cron expressions.** More flexible, but harder for non-SRE users to read and validate, and they need another library. The presets cover the requested cases.
- **Replaying every missed slot.** After a long outage this would send a burst of identical analyses and emails.
