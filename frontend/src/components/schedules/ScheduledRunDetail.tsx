import type { Api } from "../../api/client";
import { useStoredAnalysis } from "../../hooks/useStoredAnalysis";
import { formatDateTime } from "../../lib/labels";
import { ExecuteRunbook } from "../ExecuteRunbook";
import { ReportView } from "../ReportView";
import { ErrorPanel } from "../StatusPanel";

/**
 * A scheduled run's stored report. The scheduler only analyzed; running the recovery is offered
 * here with the same approval-gated execution as under a fresh report (ADR 0010).
 */
export function ScheduledRunDetail({
  api,
  analysisId,
  scheduleName,
  pollIntervalMs,
  onBack,
}: {
  api: Api;
  analysisId: string;
  scheduleName: string;
  pollIntervalMs?: number;
  onBack: () => void;
}) {
  const state = useStoredAnalysis(api, analysisId);
  const back = (
    <button type="button" onClick={onBack} className="btn-ghost">
      ← Back to schedules
    </button>
  );
  if (state.phase === "loading") {
    return (
      <div className="space-y-2">
        {back}
        <p role="status">Loading the scheduled run's report…</p>
      </div>
    );
  }
  if (state.phase === "error") {
    return (
      <div className="space-y-2">
        {back}
        <ErrorPanel title="Could not open the report" error={state.error} onDismiss={onBack} />
      </div>
    );
  }
  const { summary, report, stale } = state.detail;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {back}
        <p className="text-sm text-slate-600">
          Scheduled run of <strong>{scheduleName}</strong>, analyzed{" "}
          {formatDateTime(summary.completedAt)} from {summary.runbookLabel}.
        </p>
      </div>
      {stale && (
        <p
          role="status"
          className="rounded-xl bg-amber-50 p-3 text-amber-900 ring-1 ring-amber-200"
        >
          <span aria-hidden="true">⚠ </span>This run is from {formatDateTime(summary.completedAt)}.
          Dependency health may have changed since; run the schedule again before executing.
        </p>
      )}
      <div aria-label="Scheduled readiness report">
        <ReportView report={report} htmlUrl={api.analysisReportHtmlUrl(analysisId)} />
      </div>
      <ExecuteRunbook
        api={api}
        jobId={analysisId}
        report={report}
        pollIntervalMs={pollIntervalMs}
      />
    </div>
  );
}
