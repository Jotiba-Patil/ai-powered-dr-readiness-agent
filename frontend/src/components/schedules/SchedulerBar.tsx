import { useState } from "react";
import type { SchedulerView } from "../../api/types";
import { formatDateTime } from "../../lib/labels";
import { Icon } from "../ui/Icon";
import { PauseForm } from "./PauseForm";

/** The global switch: a banner while everything is paused, otherwise a live strip with "Pause all…". */
export function SchedulerBar({
  scheduler,
  canAct,
  onPauseAll,
  onResumeAll,
}: {
  scheduler: SchedulerView;
  canAct: boolean;
  onPauseAll: (until?: string) => void;
  onResumeAll: () => void;
}) {
  const [pausing, setPausing] = useState(false);
  const transport =
    scheduler.emailTransport === "smtp" ? "Emails are sent over SMTP." : "Emails are only logged.";
  if (scheduler.paused) {
    const until = scheduler.pauseUntil ? ` until ${formatDateTime(scheduler.pauseUntil)}` : "";
    return (
      <div
        role="status"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 p-3 text-amber-900 ring-1 ring-amber-200"
      >
        <span className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-100">
            <Icon name="pause" />
          </span>
          <span>
            All schedules are paused{until}
            {scheduler.pausedBy ? ` by ${scheduler.pausedBy}` : ""}. No new runs start.
          </span>
        </span>
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-2"
          disabled={!canAct}
          onClick={onResumeAll}
        >
          <Icon name="play" />
          Resume all
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
        <span className="flex items-center gap-2 text-sm text-slate-600">
          <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
          </span>
          <strong className="font-semibold text-emerald-800">Scheduler on</strong>
          <span className="text-slate-400" aria-hidden="true">
            ·
          </span>
          <Icon name="shield" className="h-4 w-4 text-signal-600" />
          <span>
            Scheduled runs analyze and email the runbook owner; they never execute. {transport}
          </span>
        </span>
        <button
          type="button"
          className="btn-ghost inline-flex items-center gap-1.5"
          disabled={!canAct}
          onClick={() => setPausing(true)}
        >
          <Icon name="pause" className="h-3.5 w-3.5" />
          Pause all…
        </button>
      </div>
      {pausing && (
        <PauseForm
          label="Pause all schedules"
          maxDays={scheduler.maxPauseDays}
          disabled={!canAct}
          onCancel={() => setPausing(false)}
          onPause={(until) => {
            setPausing(false);
            onPauseAll(until);
          }}
        />
      )}
    </div>
  );
}
