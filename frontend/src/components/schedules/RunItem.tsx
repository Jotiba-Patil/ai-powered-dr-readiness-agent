import type { ScheduleRun } from "../../api/types";
import { RISK_TONES, formatDateTime } from "../../lib/labels";
import {
  RUN_TONES,
  emailResult,
  relativeTime,
  runDuration,
  runResult,
} from "../../lib/scheduleLabels";
import { Badge } from "../Badge";
import { Icon } from "../ui/Icon";

const EMAIL_TEXT = { sent: "text-slate-600", failed: "text-red-700", none: "text-slate-500" };

/** One run on the timeline: when, how it was started, result, email and report link. */
export function RunItem({
  run,
  canAct,
  onOpen,
  onCancel,
}: {
  run: ScheduleRun;
  canAct: boolean;
  onOpen: () => void;
  onCancel: () => void;
}) {
  const duration = runDuration(run);
  const tone = RUN_TONES[run.state];
  return (
    <li className="relative flex flex-wrap items-center gap-x-3 gap-y-1 py-3 pl-7 text-sm">
      <span
        aria-hidden="true"
        className={`absolute top-4 left-1 h-3 w-3 rounded-full ring-4 ring-white ${run.state === "running" ? "animate-pulse" : ""}`}
        style={{ background: tone.color }}
      />
      <span className="w-56">
        <span className="tabular block font-medium whitespace-nowrap text-ink-900">
          {formatDateTime(run.startedAt)}
        </span>
        <span className="text-xs text-slate-500">
          {relativeTime(run.startedAt)}
          {duration ? ` · took ${duration}` : ""}
        </span>
      </span>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
        {run.trigger === "manual" ? "Run now" : "Scheduled"}
      </span>
      <Badge tone={tone} />
      {run.riskScore != null && run.riskLevel ? (
        <span className="flex items-center gap-2">
          <Badge
            tone={RISK_TONES[run.riskLevel]}
            text={`${run.riskScore} ${RISK_TONES[run.riskLevel].label}`}
          />
          <span className={run.rtoFeasible ? "text-emerald-800" : "font-medium text-red-800"}>
            {run.rtoFeasible ? "RTO feasible" : "RTO not feasible"}
          </span>
        </span>
      ) : (
        <span className="text-slate-600">{runResult(run)}</span>
      )}
      <span
        className={`flex items-center gap-1 text-xs ${EMAIL_TEXT[run.emailState === "sent" || run.emailState === "failed" ? run.emailState : "none"]}`}
      >
        <Icon name="mail" className="h-3.5 w-3.5" />
        <span>{emailResult(run)}</span>
      </span>
      <span className="ml-auto flex gap-1">
        {run.analysisId ? (
          <button
            type="button"
            className="btn-ghost inline-flex items-center gap-1"
            onClick={onOpen}
          >
            Open report
            <Icon name="arrow" className="h-3.5 w-3.5" />
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
            onClick={onCancel}
          >
            Cancel run
          </button>
        )}
      </span>
    </li>
  );
}
