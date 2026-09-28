import type { Api } from "../../api/client";
import type { ScheduleView } from "../../api/types";
import { useScheduleRuns } from "../../hooks/useScheduleRuns";
import { formatDateTime } from "../../lib/labels";
import { RUN_TONES, emailResult, runResult } from "../../lib/scheduleLabels";
import { Badge } from "../Badge";

/** Runs of one schedule; a stored run opens its report, a running one can be cancelled. */
export function ScheduleRuns({
  api,
  schedule,
  pollIntervalMs,
  canAct,
  onOpenRun,
  onCancel,
  onClose,
}: {
  api: Api;
  schedule: ScheduleView;
  pollIntervalMs?: number;
  canAct: boolean;
  onOpenRun: (runId: string, analysisId: string) => void;
  onCancel: (runId: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { runs, loading, error, refresh } = useScheduleRuns(api, schedule.id, pollIntervalMs);
  let body;
  if (loading) body = <p role="status">Loading runs…</p>;
  else if (error) body = <p role="alert">Runs unavailable: {error}</p>;
  else if (runs.length === 0) body = <p className="text-sm text-slate-600">No runs yet.</p>;
  else {
    body = (
      <ul className="divide-y divide-slate-200">
        {runs.map((run) => (
          <li key={run.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <span className="tabular w-40">{formatDateTime(run.startedAt)}</span>
            <span className="w-20 text-slate-500">
              {run.trigger === "manual" ? "Run now" : "Slot"}
            </span>
            <Badge tone={RUN_TONES[run.state]} />
            <span>{runResult(run)}</span>
            <span className="text-xs text-slate-500">{emailResult(run)}</span>
            <span className="ml-auto flex gap-1">
              {run.analysisId ? (
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => onOpenRun(run.id, run.analysisId ?? "")}
                >
                  Open report
                </button>
              ) : (
                run.state === "succeeded" && (
                  <span className="text-xs text-slate-500">Report not stored</span>
                )
              )}
              {run.state === "running" && (
                <button
                  type="button"
                  className="btn-ghost text-red-700"
                  disabled={!canAct}
                  onClick={() => void onCancel(run.id).then(refresh)}
                >
                  Cancel run
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <section aria-label={`Runs of ${schedule.name}`} className="card space-y-2 p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-ink-900">Runs of {schedule.name}</h3>
        <span className="flex gap-1">
          <button type="button" className="btn-ghost" onClick={refresh}>
            Refresh runs
          </button>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Close runs
          </button>
        </span>
      </div>
      {body}
    </section>
  );
}
