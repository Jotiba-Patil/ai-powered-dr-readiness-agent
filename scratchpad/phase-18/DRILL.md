# Phase 18 browser drill: uploads, monthly schedules, one date-time format

Date: 2026-09-27. Driven through the Playwright MCP tools.

## Setup
- `API_ALLOWED_DIR` pointed at a scratch copy of `mock-data` (`scratchpad/drill18-data` in the session folder), so uploads never touched the repository; `DB_PATH` in the same folder.
- API: `uv run poe dev-api` with `LLM_PROVIDER=none SCHEDULER_ENABLED=true NOTIFY_TRANSPORT=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025 NOTIFY_CONTACTS_FILE=<copy>/contacts.json UI_BASE_URL=http://localhost:5173`; SMTP catcher `aiosmtpd` on 127.0.0.1:1025; UI `uv run poe dev-ui`.
- Upload test files in `.playwright-mcp/` (git-ignored; the Playwright tool only reads files inside the repository): `notes.md` (not a runbook) and `My DR Runbook.md` (a copy of `estimate-service.md`).

## Steps and results
| # | Step | Result |
|---|---|---|
| 1 | Schedules tab, name "Jotiba" | Form shows "Timezone **Asia/Calcutta** (from your browser)", read-only; Repeat offers Hourly / Daily / Weekly / **Monthly** |
| 2 | **Upload runbook…** `notes.md` | Refused: "Not saved: no recovery steps found in runbook"; nothing selected, nothing written |
| 3 | **Upload runbook…** `My DR Runbook.md` | "Saved as uploads/my-dr-runbook.md (Estimate Service)", selected in the list; the file on disk is byte-identical to the upload (`cmp`); the repository's `mock-data/uploads` does not exist |
| 4 | Name "Monthly drill", Monthly, Day of month "31 (or the last day)", 06:00 | "Email goes to: alice.chen@example.com" |
| 5 | **Create schedule** | Row: "Monthly on day 31 (last day in shorter months) 06:00 Asia/Calcutta", next run **30 Sep 2026, 06:00 UTC+05:30** (September has 30 days). API stores `nextRunAt: 2026-09-30T00:30:00Z` (UTC) |
| 6 | **Run now** | Run listed at "27 Sep 2026, 22:27 UTC+05:30"; succeeded, "Emailed alice.chen@example.com" |
| 7 | **Open report** | "analyzed 27 Sep 2026, 22:27 UTC+05:30" in both the run line and the report header (the header used the browser's locale format before this phase) |
| 8 | **Export HTML** link | `…/report.html?tz=Asia%2FCalcutta`; content "Analyzed: 27 Sep 2026, 22:27 UTC+05:30"; without `tz`: "Analyzed: 27 Sep 2026, 16:57 UTC" |
| 9 | Email (SMTP catcher) | "Run: 27 Sep 2026, 22:27 UTC+05:30 (run now)" (the schedule's zone) |
| 10 | `dr-agent schedule list` on the drill database | "next 30 Sep 2026, 06:00 UTC+05:30" (machine zone); with `DISPLAY_TIMEZONE=UTC`: "next 30 Sep 2026, 00:30 UTC" |

Screenshot: `drill-monthly-upload-local-time.png`. The one browser console error during the drill is the refused upload in step 2 (HTTP 422), which is expected.

Afterwards the API, UI and SMTP catcher were stopped. The leftover Vite process (PID 24476) was checked to be `vite.js` and killed; ports 8000, 5173 and 1025 are free.
