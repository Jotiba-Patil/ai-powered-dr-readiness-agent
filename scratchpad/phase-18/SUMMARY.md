# Phase 18 summary: monthly schedules, saved runbook uploads, browser timezone, one date-time format

Date: 2026-09-27. Status: done, exit criteria met. Not committed (owner asked for no commits).

## Owner requests and decisions (2026-09-27)
1. Monthly schedules: day 1-31, where a day the month lacks runs on its last day, plus "last day of month".
2. Upload a runbook and save it in a folder: its own folder, never overwritten, runbooks only.
3. Timezone: first planned as a searchable list; the owner changed it to **not editable, taken from the browser**.
4. Times: stored in UTC, shown in local time, and then **consistent at all places** (dashboard, CLI, HTML export, emails).

## Before starting
Re-verified Phases 0-17: ruff clean, 282 files formatted, `mypy --strict` no issues in 162 files, eslint/tsc/prettier clean; 1147 backend tests at 98.96%, 137 UI tests (96.55% lines); `pip-audit` and `npm audit` clean. Design section 18 written before the code.

## What was built
| Area | Files |
|---|---|
| Monthly cadence | `scheduling/models.py` (`MonthlyCadence`, in the `Cadence` union), `scheduling/next_run.py` (`_monthly()`, `describe()`); no migration (cadence is JSON) |
| Uploads | `runbook_uploads.py` (`RunbookUploads`, `safe_stem()`), `api/body_upload.py` (JSON or multipart reader, exact text), `POST /api/v1/dr/samples/runbooks` and upload listing in `api/routes_samples.py`, `UPLOAD_REQUEST_BODY` in `api/openapi.py`, `UploadsDisabledError` (403); `api/body.py` helpers made public |
| One time format | `utils/timefmt.py` (`display_time()`, `zone_or_none()`); CLI (`cli_history.py`, `cli_schedule.py`, `cli_execute_view.py`), emails (`notify/message.py`), HTML export (`formatters/format_html.py`, template, `?tz=` on both report routes); frontend `formatDateTime()` and `browserTimezone()` in `lib/labels.ts`, used by every view (Schedules, History, Historical insights, report header, audit log) |
| UI | `CadenceFields` (Monthly, day of month, last day), `RunbookPicker` (list + **Upload runbook…**), `ScheduleForm` (read-only browser timezone), `useSamples.reload`, `api.uploadRunbook()`, `tzQuery()` on HTML export links, `UploadedRunbook` type |
| Config | `DISPLAY_TIMEZONE`, `RUNBOOK_UPLOADS_ENABLED`, `RUNBOOK_UPLOAD_DIR`, `RUNBOOK_UPLOAD_MAX_FILES`; new `config_extras.py` (email, display, upload settings, inherited by `Settings`) |
| Delivery | `docker/api.Dockerfile` creates `/app/mock-data/uploads` for the app user; Compose `dr-agent-uploads` volume and `RUNBOOK_UPLOADS_ENABLED`; `mock-data/uploads/` in `.gitignore` and `.dockerignore`; `.env.example` |
| Generated | `poe gen-api` (`MonthlyCadence`, upload endpoint and schemas, `tz` query) |
| Docs | design section 18 (18.1-18.6), `docs/IMPLEMENTATION_PLAN.md` (Phase 18, Verification), README (features, dashboard, CLI, API, scheduled analysis, layout, Docker, configuration, security notes, roadmap), `docs/SECURITY_GUARDRAILS.md` (threat row, section 7 rows, deployment, known gap), `CLAUDE.md`, the three rule files, phase-workflow skill, `/demo` |

## Tests
- Backend, 54 new: `test_scheduling_monthly.py` (21: clamping in 30-day months and February in normal and leap years, "last", month and year rollover, DST in Berlin, a zone ahead of UTC, descriptions, invalid days), `test_timefmt.py` (shared cases with the frontend), `test_runbook_uploads.py` (names, no overwrite, parse check, count limit, folder containment), `integration/test_api_uploads.py` (JSON and multipart, listing, analyze and schedule an upload, refusals, limits, disabled, HTML export with `tz`), CLI time zone test, config tests.
- HTML golden snapshot `backend/tests/fixtures/expected_report.html` updated **on purpose**: only its "Analyzed" line changed, from `2026-09-22 10:00:00+00:00` to `22 Sep 2026, 10:00 UTC`.
- Existing tests updated to the new format (CLI history and schedule, email, History and Schedules views, link builders with `?tz=UTC`).
- UI, 11 new: `lib/formatDateTime.test.ts` (the backend's cases), `RunbookPicker.test.tsx` (upload success and refusal, monthly day and last day), read-only timezone in `ScheduleForm.test.tsx`, `uploadRunbook` in `client.test.ts`.
- Browser drill: `DRILL.md` and `drill-monthly-upload-local-time.png` in this folder.

## Gate (final run)
| Check | Result |
|---|---|
| `uv run poe lint` | ruff clean, 290 files formatted, `mypy --strict` no issues in 166 files, eslint/tsc/prettier clean |
| `uv run poe test` | 1201 backend tests passed, 98.83%; 148 UI tests passed, 96.69% lines |
| `uv run poe audit` | no known vulnerabilities; npm 0 vulnerabilities |
| File sizes | backend files under 200 lines (`config.py` 137 after the split), components under 150; only the generated `schema.d.ts` is larger |

## Decisions made while building (open for review)
| # | Decision | Why |
|---|---|---|
| P18-1 | Display format `28 Sep 2026, 11:30 UTC+05:30`, numeric offset | Identical in Python and browsers; abbreviations differ ("IST", "GMT+5:30", "India Standard Time") |
| P18-2 | Month names from a fixed list on both sides | Intl's `en-GB` prints "Sept", Python prints "Sep" |
| P18-3 | `DISPLAY_TIMEZONE` for the CLI (default: the machine's zone) | On Windows `TZ` has no effect, so tests and users need a way to choose; the dashboard needs none (browser zone) |
| P18-4 | HTML export takes `?tz=`; the dashboard adds the browser's zone; UTC without it | A downloaded file cannot know the reader's zone later |
| P18-5 | `config_extras.py` for email, display and upload settings | Keeps `config.py` under 200 lines; env names unchanged |
| P18-6 | Uploads: exclusive create reserves the name, then a temporary file replaces the empty placeholder | Never overwrites, and a reader never sees half a file |
| P18-7 | Upload requests keep the runbook text exactly (no whitespace stripping) | Found by a test: the base model trimmed the final newline |
| P18-8 | `GET /dr/samples/file` still trims text (unchanged) | Existing behaviour for every sample; outside this phase |
| P18-9 | Image creates `/app/mock-data/uploads` owned by the app user; `mock-data/uploads/` ignored by git and Docker | A new volume copies the mount point's ownership; uploads are user content, not repository data |
| P18-10 | The frontend client also exposes `uploadRunbook()` as JSON (the file is read in the browser); multipart stays for `curl` | One typed call through the generated client |

## Notes
- Two edit-script mistakes were caught at once: a heredoc the shell could not parse (the script was written to a file instead), and an escaped `\n` that became a real line break in a test (fixed with the Edit tool).
- The drill wrote uploads only into a scratch copy of `mock-data`; the repository has no `mock-data/uploads`.

## Next
Nothing planned. Docker is still not installed here, so the Compose changes (uploads volume, image folder) are checked by YAML parsing and the CI `docker` job.
