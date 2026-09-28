---
paths:
  - "frontend/**/*.{ts,tsx,css}"
---

# React frontend rules

- React 18 function components, TypeScript strict, no `any`. Vite, Tailwind, Recharts.
- API types come from the backend OpenAPI schema (generated client). Do not hand-write duplicate response types.
- Fetch through a single typed API client module. Handle loading, error and "AI analysis unavailable" states for every view.
- Components under 150 lines. Presentational components take props; data fetching lives in hooks.
- Accessibility: semantic elements, labels for inputs, color is never the only severity signal (add text or icon).
- Execution UI lives under an analysis report (`ExecutionSection`), never in its own tab or page, and is created from the analysis job id. It is offered under a fresh report (Analyze tab) and under a scheduled run's stored report (`ScheduledRunDetail`, ADR 0010), nowhere else. The server decides everything; components only offer actions that fit the state. Tool results, AI rationales and audit payloads are shown as text. Test stubs for the execution API live in `src/test/executionFixtures.ts`.
- The History tab (`components/history/`) lists stored analyses; an opened analysis shows `ReportView` plus `PastExecutions`, a **read-only** record of its runs (locked `StepCard`s, `AuditPanel`). It never offers to create or change a run: executions start only from a fresh report on the Analyze tab or from a scheduled run's report on the Schedules tab. Stored runbook text is only offered as a download link. Test stubs for the history API live in `src/test/historyFixtures.ts`.
- The Schedules tab (`components/schedules/`) lists schedules and their runs; every change needs "Your name" and goes through `useSchedules().act()`. Scheduled runs never execute by themselves: a run's report offers the normal `ExecuteRunbook`. Email links (`#/schedules/{id}/runs/{runId}`) are parsed by `parseScheduleHash()` on load and on `hashchange`. Test stubs for the schedule API live in `src/test/scheduleFixtures.ts`.
- Times: show every timestamp with `formatDateTime()` from `lib/labels.ts` (browser zone, e.g. `28 Sep 2026, 11:30 UTC+05:30`); never `toLocaleString()` or slicing ISO strings. Server-rendered HTML links carry `tzQuery()`. The schedule form's timezone is the browser's (`browserTimezone()`), shown read-only. Runbook uploads go through `RunbookPicker` / `api.uploadRunbook()`.
- `HistoricalInsights` renders the report's `historicalInsights` (server-measured facts); step cards get the matching `StepHistory` from the report through `ExecutionPanel`'s `history` prop, with no extra request. `makeHistory()` in `src/test/historyFixtures.ts`.
- Every pending execution request passes a `Progress` label to `useExecution.run()`; `ProgressNote` shows it (role `status`, elapsed seconds) so disabled buttons are always explained. A "Run in progress" note shows while `callingTools(execution)`.
- Visual language (Tailwind v4 theme in `src/index.css`): `ink-*` chrome, one `signal-*` accent, `card`, `btn-primary`, `btn-ghost` and `tabular` utilities; icons from `components/ui/Icon.tsx` (inline SVG, `aria-hidden`, always next to text). Reuse these rather than new one-off colours. Keep accessible names stable when restyling (tests and screen readers rely on them); a button with extra visible text gets `aria-label` plus `aria-describedby`.
- Tests with vitest and React Testing Library. Query by role or label, not by class names.
- No secrets or model names hardcoded. Use `VITE_API_BASE_URL`.
