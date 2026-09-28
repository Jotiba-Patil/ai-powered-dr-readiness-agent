import { useState } from "react";
import type { ScheduleView } from "../../api/types";
import { formatDateTime } from "../../lib/labels";
import { RUN_TONES, runResult, scheduleState } from "../../lib/scheduleLabels";
import { Badge } from "../Badge";
import { PauseForm } from "./PauseForm";

export interface ScheduleActions {
  open: (scheduleId: string) => void;
  runNow: (scheduleId: string) => void;
  pause: (scheduleId: string, until?: string) => void;
  resume: (scheduleId: string) => void;
  remove: (scheduleId: string) => void;
}

/** One row per schedule; actions need a name (`canAct`) and are off while a change is pending. */
export function ScheduleList({
  schedules,
  actions,
  canAct,
  maxPauseDays,
}: {
  schedules: ScheduleView[];
  actions: ScheduleActions;
  canAct: boolean;
  maxPauseDays: number;
}) {
  const [pausing, setPausing] = useState<string | null>(null);
  if (schedules.length === 0) {
    return <p className="text-sm text-slate-600">No schedules yet. Create one below.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs text-slate-500 uppercase">
        <tr>
          <th className="py-2">Schedule</th>
          <th>When</th>
          <th>Next run</th>
          <th>Last run</th>
          <th>State</th>
          <th>
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {schedules.map((s) => (
          <tr key={s.id} className="border-t border-slate-200 align-top">
            <td className="py-2">
              <button
                type="button"
                className="font-medium text-signal-700 underline"
                onClick={() => actions.open(s.id)}
              >
                {s.name}
              </button>
              <span className="block text-xs text-slate-500">{s.runbookPath}</span>
            </td>
            <td>{s.description}</td>
            <td className="tabular">{s.nextRunAt ? formatDateTime(s.nextRunAt) : "—"}</td>
            <td>
              {s.lastRun ? (
                <span className="flex flex-col gap-1">
                  <Badge tone={RUN_TONES[s.lastRun.state]} />
                  <span className="text-xs text-slate-600">{runResult(s.lastRun)}</span>
                </span>
              ) : (
                "Never run"
              )}
            </td>
            <td>{scheduleState(s)}</td>
            <td className="space-y-2 py-2">
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={!canAct}
                  aria-label={`Run ${s.name} now`}
                  onClick={() => actions.runNow(s.id)}
                >
                  Run now
                </button>
                {s.enabled ? (
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={!canAct}
                    aria-label={`Pause ${s.name}`}
                    onClick={() => setPausing(s.id)}
                  >
                    Pause…
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={!canAct}
                    aria-label={`Resume ${s.name}`}
                    onClick={() => actions.resume(s.id)}
                  >
                    Resume
                  </button>
                )}
                <button
                  type="button"
                  className="btn-ghost text-red-700"
                  disabled={!canAct}
                  aria-label={`Delete ${s.name}`}
                  onClick={() => actions.remove(s.id)}
                >
                  Delete
                </button>
              </div>
              {pausing === s.id && (
                <PauseForm
                  label={`Pause ${s.name}`}
                  maxDays={maxPauseDays}
                  disabled={!canAct}
                  onCancel={() => setPausing(null)}
                  onPause={(until) => {
                    setPausing(null);
                    actions.pause(s.id, until);
                  }}
                />
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
