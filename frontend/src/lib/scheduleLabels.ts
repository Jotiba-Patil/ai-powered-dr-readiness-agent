// Labels for schedules and their runs. As elsewhere, color is never the only signal.
import type { RunState, ScheduleRun, ScheduleView } from "../api/types";
import { formatDateTime, type Tone } from "./labels";

export const RUN_TONES: Record<RunState, Tone> = {
  running: { icon: "●", label: "Running", className: "bg-sky-100 text-sky-800", color: "#0284c7" },
  succeeded: {
    icon: "✔",
    label: "Succeeded",
    className: "bg-emerald-100 text-emerald-800",
    color: "#059669",
  },
  failed: { icon: "✖", label: "Failed", className: "bg-red-100 text-red-800", color: "#dc2626" },
  cancelled: {
    icon: "■",
    label: "Cancelled",
    className: "bg-slate-100 text-slate-700",
    color: "#475569",
  },
};

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

/** "Active", "Paused by Bob" or "Paused until 2026-09-28 06:00 UTC by Bob". */
export function scheduleState(schedule: ScheduleView): string {
  if (schedule.enabled) return "Active";
  const until = schedule.pauseUntil ? ` until ${formatDateTime(schedule.pauseUntil)}` : "";
  return `Paused${until}${schedule.pausedBy ? ` by ${schedule.pausedBy}` : ""}`;
}

/** Risk and RTO of a finished run, or why it did not produce a report. */
export function runResult(run: ScheduleRun): string {
  if (run.riskScore != null && run.riskLevel) {
    const rto = run.rtoFeasible ? "RTO feasible" : "RTO not feasible";
    return `Risk ${run.riskScore} ${run.riskLevel.toLowerCase()} · ${rto}`;
  }
  if (run.state === "running") return "Analyzing…";
  if (run.state === "cancelled") return "Cancelled";
  return run.errorCode ? `Failed (${run.errorCode})` : "Failed";
}

export function emailResult(run: ScheduleRun): string {
  if (!run.emailState) return "No email yet";
  if (run.emailState === "sent") return `Emailed ${run.emailTo?.join(", ")}`;
  if (run.emailState === "failed") return "Email failed";
  return "No recipient";
}

/** `<input type="datetime-local">` value (browser time) -> ISO string, or undefined when empty. */
export function localInputToIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export interface ScheduleLink {
  scheduleId: string;
  runId: string | null;
}

/** Email links open `#/schedules/{scheduleId}/runs/{runId}` (the app has no router). */
export function parseScheduleHash(hash: string): ScheduleLink | null {
  const match = /^#\/schedules\/([A-Za-z0-9_-]{1,64})(?:\/runs\/([A-Za-z0-9_-]{1,64}))?\/?$/.exec(
    hash,
  );
  const scheduleId = match?.[1];
  return scheduleId ? { scheduleId, runId: match?.[2] ?? null } : null;
}

/** Leaves an email link, so a reload shows the list instead of reopening that run. */
export function clearScheduleHash(): void {
  if (window.location.hash) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}
