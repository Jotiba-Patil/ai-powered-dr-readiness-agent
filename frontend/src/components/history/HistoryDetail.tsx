import type { Api } from "../../api/client";
import { useStoredAnalysis } from "../../hooks/useStoredAnalysis";
import { utcMinute } from "../../lib/labels";
import { ReportView } from "../ReportView";
import { ErrorPanel } from "../StatusPanel";
import { PastExecutions } from "./PastExecutions";

/** A stored analysis: its report, a runbook download and what its executions did (read-only). */
export function HistoryDetail({
  api,
  analysisId,
  onBack,
}: {
  api: Api;
  analysisId: string;
  onBack: () => void;
}) {
  const state = useStoredAnalysis(api, analysisId);
  const back = (
    <button type="button" onClick={onBack} className="btn-ghost">
      ← Back to history
    </button>
  );
  if (state.phase === "loading") {
    return (
      <div className="space-y-2">
        {back}
        <p role="status">Loading analysis…</p>
      </div>
    );
  }
  if (state.phase === "error") {
    return (
      <div className="space-y-2">
        {back}
        <ErrorPanel title="Could not open the analysis" error={state.error} onDismiss={onBack} />
      </div>
    );
  }
  const { summary, report, provenance, stale } = state.detail;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {back}
        <p className="text-sm text-slate-600">
          Analyzed {utcMinute(summary.completedAt)} from {summary.runbookLabel} (
          {provenance.llmModel ?? "rules only"}).{" "}
          <a
            href={api.analysisRunbookUrl(analysisId)}
            className="font-medium text-signal-700 underline"
          >
            Download runbook
          </a>
        </p>
      </div>
      {stale && (
        <p
          role="status"
          className="rounded-xl bg-amber-50 p-3 text-amber-900 ring-1 ring-amber-200"
        >
          <span aria-hidden="true">⚠ </span>This analysis is from {utcMinute(summary.completedAt)}.
          Dependency health may have changed since; analyze the runbook again before running it.
        </p>
      )}
      <div aria-label="Stored readiness report">
        <ReportView report={report} htmlUrl={api.analysisReportHtmlUrl(analysisId)} />
      </div>
      <PastExecutions api={api} analysisId={analysisId} />
    </div>
  );
}
