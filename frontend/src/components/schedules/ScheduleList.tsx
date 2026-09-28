import { Fragment, useState } from "react";
import type { ScheduleView } from "../../api/types";
import { Icon } from "../ui/Icon";
import { PauseForm } from "./PauseForm";
import { ScheduleRow } from "./ScheduleRow";

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
  openId,
}: {
  schedules: ScheduleView[];
  actions: ScheduleActions;
  canAct: boolean;
  maxPauseDays: number;
  openId?: string | null;
}) {
  const [pausing, setPausing] = useState<string | null>(null);
  if (schedules.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 p-8 text-center">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-signal-500/10 text-signal-700">
          <Icon name="calendar" className="h-5 w-5" />
        </span>
        <p className="font-medium text-ink-900">No schedules yet. Create one below.</p>
        <p className="max-w-md text-sm text-slate-600">
          A schedule re-checks a runbook every hour, day, week or month and emails the owner a
          facts-only summary.
        </p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
          <tr>
            <th className="px-3 py-2 font-semibold">Schedule</th>
            <th className="px-3 font-semibold">When</th>
            <th className="px-3 font-semibold">Next run</th>
            <th className="px-3 font-semibold">Last run</th>
            <th className="px-3 font-semibold">State</th>
            <th className="px-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {schedules.map((s) => (
            <Fragment key={s.id}>
              <ScheduleRow
                schedule={s}
                actions={actions}
                canAct={canAct}
                open={openId === s.id}
                onPause={() => setPausing(s.id)}
              />
              {pausing === s.id && (
                <tr>
                  <td colSpan={6} className="px-3 pb-3">
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
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
