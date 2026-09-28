import { useState } from "react";
import type { SchedulerView } from "../../api/types";
import { formatDateTime } from "../../lib/labels";
import { PauseForm } from "./PauseForm";

/** The global pause switch: a banner while everything is paused, otherwise "Pause all…". */
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
        className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-50 p-3 text-amber-900 ring-1 ring-amber-200"
      >
        <span>
          <span aria-hidden="true">⏸ </span>All schedules are paused{until}
          {scheduler.pausedBy ? ` by ${scheduler.pausedBy}` : ""}. No new runs start.
        </span>
        <button type="button" className="btn-primary" disabled={!canAct} onClick={onResumeAll}>
          Resume all
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
        <span>
          Scheduled runs analyze and email the runbook owner; they never execute. {transport}
        </span>
        <button
          type="button"
          className="btn-ghost"
          disabled={!canAct}
          onClick={() => setPausing(true)}
        >
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
