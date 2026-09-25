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
- Execution UI lives under the analysis report (`ExecutionSection`), never in its own tab or page, and is created from the analysis job id. The server decides everything; components only offer actions that fit the state. Tool results, AI rationales and audit payloads are shown as text. Test stubs for the execution API live in `src/test/executionFixtures.ts`.
- The History tab (`components/history/`) lists stored analyses; an opened analysis shows `ReportView` plus `PastExecutions`, a **read-only** record of its runs (locked `StepCard`s, `AuditPanel`). It never offers to create or change a run: executions start only from a fresh report on the Analyze tab. Stored runbook text is only offered as a download link. Test stubs for the history API live in `src/test/historyFixtures.ts`.
- `HistoricalInsights` renders the report's `historicalInsights` (server-measured facts); step cards get the matching `StepHistory` from the report through `ExecutionPanel`'s `history` prop, with no extra request. `makeHistory()` in `src/test/historyFixtures.ts`.
- Every pending execution request passes a `Progress` label to `useExecution.run()`; `ProgressNote` shows it (role `status`, elapsed seconds) so disabled buttons are always explained. A "Run in progress" note shows while `callingTools(execution)`.
- Visual language (Tailwind v4 theme in `src/index.css`): `ink-*` chrome, one `signal-*` accent, `card`, `btn-primary`, `btn-ghost` and `tabular` utilities; icons from `components/ui/Icon.tsx` (inline SVG, `aria-hidden`, always next to text). Reuse these rather than new one-off colours. Keep accessible names stable when restyling (tests and screen readers rely on them); a button with extra visible text gets `aria-label` plus `aria-describedby`.
- Tests with vitest and React Testing Library. Query by role or label, not by class names.
- No secrets or model names hardcoded. Use `VITE_API_BASE_URL`.
