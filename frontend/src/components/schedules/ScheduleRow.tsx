import type { ScheduleView } from "../../api/types";
import { RISK_TONES, formatDateTime, type Tone } from "../../lib/labels";
import { RUN_TONES, relativeTime, runResult } from "../../lib/scheduleLabels";
import { Badge } from "../Badge";
import { Icon } from "../ui/Icon";
import { RowActions } from "./RowActions";
import type { ScheduleActions } from "./ScheduleList";

const ACTIVE: Tone = {
  icon: "●",
  label: "Active",
  className: "bg-emerald-100 text-emerald-800",
  color: "#059669",
};
const PAUSED: Tone = {
  icon: "⏸",
  label: "Paused",
  className: "bg-amber-100 text-amber-800",
  color: "#d97706",
};

function LastRun({ schedule }: { schedule: ScheduleView }) {
  const run = schedule.lastRun;
  if (!run) return <span className="text-slate-500">Never run</span>;
  return (
    <span className="flex flex-col items-start gap-1">
      <span className="flex flex-wrap items-center gap-1">
        <Badge tone={RUN_TONES[run.state]} />
        {run.riskScore != null && run.riskLevel && (
          <Badge
            tone={RISK_TONES[run.riskLevel]}
            text={`${run.riskScore} ${RISK_TONES[run.riskLevel].label}`}
          />
        )}
      </span>
      <span className="text-xs text-slate-500">
        {run.riskScore != null ? (
          <span className={run.rtoFeasible ? "text-emerald-800" : "font-medium text-red-800"}>
            {run.rtoFeasible ? "RTO feasible" : "RTO not feasible"}
          </span>
        ) : (
          runResult(run)
        )}
        {" · "}
        {relativeTime(run.startedAt)}
      </span>
    </span>
  );
}

/** One schedule: name (opens its runs), cadence, next and last run, state and actions. */
export function ScheduleRow({
  schedule,
  actions,
  canAct,
  open,
  onPause,
}: {
  schedule: ScheduleView;
  actions: ScheduleActions;
  canAct: boolean;
  open: boolean;
  onPause: () => void;
}) {
  return (
    <tr
      className={`border-t border-slate-100 align-top transition hover:bg-signal-500/5 ${open ? "bg-signal-500/5 shadow-[inset_3px_0_0_var(--color-signal-500)]" : ""}`}
    >
      <td className="px-3 py-2.5">
        <button
          type="button"
          aria-expanded={open}
          title="Show this schedule's runs"
          className="group inline-flex items-center gap-1 font-medium text-ink-900 hover:text-signal-700"
          onClick={() => actions.open(schedule.id)}
        >
          {schedule.name}
          <Icon
            name="chevron"
            className={`h-3.5 w-3.5 text-slate-400 transition group-hover:text-signal-600 ${open ? "" : "-rotate-90"}`}
          />
        </button>
        <span className="flex items-center gap-1 text-xs whitespace-nowrap text-slate-500">
          <Icon name="file" className="h-3 w-3" />
          {schedule.runbookPath}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <span className="inline-flex items-center gap-1.5 text-slate-700">
          <Icon name="clock" className="h-3.5 w-3.5 text-slate-400" />
          {schedule.description}
        </span>
      </td>
      <td className="tabular px-3 py-2.5">
        {schedule.nextRunAt ? (
          <>
            <span className="block font-medium text-ink-900">
              {relativeTime(schedule.nextRunAt)}
            </span>
            <span className="text-xs whitespace-nowrap text-slate-500">
              {formatDateTime(schedule.nextRunAt)}
            </span>
          </>
        ) : (
          <span className="text-slate-500">—</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <LastRun schedule={schedule} />
      </td>
      <td className="px-3 py-2.5">
        <Badge tone={schedule.enabled ? ACTIVE : PAUSED} />
        {!schedule.enabled && (schedule.pauseUntil || schedule.pausedBy) && (
          <span className="mt-1 block text-xs text-slate-500">
            {schedule.pauseUntil ? `until ${formatDateTime(schedule.pauseUntil)}` : ""}
            {schedule.pausedBy ? ` by ${schedule.pausedBy}` : ""}
          </span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <RowActions schedule={schedule} actions={actions} canAct={canAct} onPause={onPause} />
      </td>
    </tr>
  );
}
