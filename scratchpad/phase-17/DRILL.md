# Phase 17 browser drill: scheduled analysis end to end

Date: 2026-09-27. Driven through the Playwright MCP tools (no script file; each step and its check is listed here).

## Setup
- SMTP catcher: `uv run python -u -m aiosmtpd -n -l 127.0.0.1:1025`. It stands in for Mailpit because Docker is not installed on this machine.
- API: `uv run poe dev-api` with `LLM_PROVIDER=none SCHEDULER_ENABLED=true EXECUTION_ENABLED=true EXECUTION_ALLOW_LIVE=true NOTIFY_TRANSPORT=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025 NOTIFY_CONTACTS_FILE=mock-data/contacts.json NOTIFY_DEFAULT_EMAIL=dr-team@example.com UI_BASE_URL=http://localhost:5173` and `DB_PATH` in the session scratchpad (not the repository).
- UI: `uv run poe dev-ui`, http://localhost:5173.
- `GET /api/v1/scheduler` returned `emailTransport: smtp`, `defaultRecipient: true`, `allowedDomains: ["example.com"]`; the log showed `scheduler_opened` and `api_started ... scheduler_enabled=True`.

## Steps and results
| # | Step | Result |
|---|---|---|
| 1 | Open the app, click **Schedules** | Empty list, "Pause all…" disabled until a name is entered; timezone prefilled with the browser's (`Asia/Calcutta`) |
| 2 | Name "Jotiba"; new schedule "Estimate hourly drill", `runbooks/estimate-service-executable.md`, `inventories/healthy.json`, Hourly | "Email goes to: alice.chen@example.com" (owner from the contact directory) |
| 3 | **Create schedule** | Row: "Hourly at :00 Asia/Calcutta", next run `2026-09-27 15:30 UTC` (21:00 IST, correct), "Never run", "Active" |
| 4 | **Run now** | Runs panel opened: Running → Succeeded, "Risk 0 low · RTO feasible", "Emailed alice.chen@example.com" (a rules-only CLI analysis of the same runbook also scores 0 with no gaps) |
| 5 | **Open report** | Stored report plus **Execute this runbook…** |
| 6 | **Execute this runbook…** → **Create dry run** | Dry run created (`drill-dry-run-from-scheduled-run.png`); `GET /analyses/{id}/executions` lists it: `dry_run CREATED Jotiba`, linked to the scheduled analysis |
| 7 | **Run now** again, read the SMTP catcher | Subject `[DR readiness] Estimate-Service: LOW risk (0/100)`, To `alice.chen@example.com`, run time in IST, owner, risk, RTO 55 of 60 min (buffer 5), gap/SPOF/dependency counts, "AI analysis: unavailable (rules only)", dashboard link; no runbook or model text |
| 8 | Open the email link in a fresh tab | Report of that run opened directly |
| 9 | Open the email link in the already open tab | **Bug:** nothing happened (hash read only on load). Fixed with a `hashchange` listener, retested: opens |
| 10 | Linked run header | **Bug:** said "this schedule". Fixed to show "Estimate hourly drill", retested |
| 11 | **Pause…** until tomorrow 09:00 local | "Paused until 2026-09-28 03:30 UTC by Jotiba" (09:00 IST, correct), next run "—" |
| 12 | **Pause all…** → **Pause** | Banner "All schedules are paused by Jotiba. No new runs start." with **Resume all** (`drill-paused.png`) |
| 13 | **Resume all**, **Resume** the schedule | API: `paused False`; schedule enabled, next run `15:30 UTC`, `pauseUntil` null |
| 14 | `dr-agent schedule list` on the same database | `... Hourly at :00 Asia/Calcutta  next 2026-09-27 15:30 UTC  last: succeeded, risk 0 LOW, RTO feasible, email sent` |

Also changed after the drill: "Back to schedules" clears the email-link hash (so a reload shows the list), and the create form clears its name and recipients after a successful create.

Afterwards the API, UI and SMTP catcher were stopped. The Vite process that outlives the task (PID 17772) was confirmed to be `vite.js` and then killed, leaving ports 8000, 5173 and 1025 free.
