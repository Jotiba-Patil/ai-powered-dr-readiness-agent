import type { Api } from "../../api/client";
import type { ScheduleView } from "../../api/types";
import { useScheduleRuns } from "../../hooks/useScheduleRuns";
import { Icon } from "../ui/Icon";
import { RunItem } from "./RunItem";

/** Runs of one schedule as a timeline; a stored run opens its report, a running one can be cancelled. */
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
  else if (runs.length === 0) {
    body = (
      <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-600">
        No runs yet. Use <strong>Run now</strong> to try it, or wait for the next slot.
      </p>
    );
  } else {
    body = (
      <ul className="relative divide-y divide-slate-100 before:absolute before:top-5 before:bottom-5 before:left-[9px] before:w-px before:bg-slate-200">
        {runs.map((run) => (
          <RunItem
            key={run.id}
            run={run}
            canAct={canAct}
            onOpen={() => onOpenRun(run.id, run.analysisId ?? "")}
            onCancel={() => void onCancel(run.id).then(refresh)}
          />
        ))}
      </ul>
    );
  }
  return (
    <section aria-label={`Runs of ${schedule.name}`} className="card overflow-hidden">
      <div className="h-1 bg-gradient-to-r from-signal-500 to-transparent" aria-hidden="true" />
      <div className="space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold text-ink-900">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-signal-500/10 text-signal-700">
                <Icon name="history" />
              </span>
              Runs of {schedule.name}
            </h3>
            <p className="mt-0.5 text-sm text-slate-600">
              {schedule.description} · {schedule.runbookPath}
              {schedule.createdBy ? ` · created by ${schedule.createdBy}` : ""}
            </p>
          </div>
          <span className="flex gap-1">
            <button
              type="button"
              className="btn-ghost inline-flex items-center gap-1.5"
              onClick={refresh}
            >
              <Icon name="refresh" className="h-3.5 w-3.5" />
              Refresh runs
            </button>
            <button
              type="button"
              className="btn-ghost inline-flex items-center gap-1.5"
              onClick={onClose}
            >
              <Icon name="close" className="h-3.5 w-3.5" />
              Close runs
            </button>
          </span>
        </div>
        {body}
      </div>
    </section>
  );
}
