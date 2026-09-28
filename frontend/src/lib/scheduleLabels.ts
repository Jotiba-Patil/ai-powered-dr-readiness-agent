// Labels for schedules and their runs. As elsewhere, color is never the only signal.
import type { Cadence, RunState, ScheduleRun, ScheduleView } from "../api/types";
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

/** "Every Monday at 06:00 (Asia/Calcutta)": a schedule's cadence in plain words. */
export function cadenceSentence(cadence: Cadence, timezone: string): string {
  if (cadence.kind === "hourly") {
    return `Every hour at ${String(cadence.minute).padStart(2, "0")} minutes past`;
  }
  const at = `at ${cadence.time} (${timezone})`;
  if (cadence.kind === "daily") return `Every day ${at}`;
  if (cadence.kind === "weekly") {
    const day = cadence.weekday.charAt(0).toUpperCase() + cadence.weekday.slice(1);
    return `Every ${WEEKDAY_NAMES[day] ?? day} ${at}`;
  }
  if (cadence.day === "last") return `On the last day of every month ${at}`;
  return `On day ${cadence.day} of every month ${at}`;
}

const WEEKDAY_NAMES: Record<string, string> = {
  Mon: "Monday",
  Tue: "Tuesday",
  Wed: "Wednesday",
  Thu: "Thursday",
  Fri: "Friday",
  Sat: "Saturday",
  Sun: "Sunday",
};

/** "in 25 min", "3 h ago", "in 2 days"; empty for an unreadable time. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  if (Number.isNaN(diff)) return "";
  const total = Math.round(Math.abs(diff) / 60_000);
  if (total < 1) return diff >= 0 ? "in under a minute" : "just now";
  let text = `${total} min`;
  if (total >= 48 * 60) text = `${Math.round(total / 1440)} days`;
  else if (total >= 60) text = `${Math.round(total / 60)} h`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

/** How long a finished run took, e.g. "2 min" or "45 s"; null while it runs. */
export function runDuration(run: ScheduleRun): string | null {
  if (!run.finishedAt) return null;
  const seconds = Math.max(0, (Date.parse(run.finishedAt) - Date.parse(run.startedAt)) / 1000);
  if (Number.isNaN(seconds)) return null;
  return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}

/** A last run someone should look at: failed, high risk, RTO not feasible or email failed. */
export function needsAttention(schedule: ScheduleView): boolean {
  const run = schedule.lastRun;
  if (!run) return false;
  return (
    run.state === "failed" ||
    run.riskLevel === "HIGH" ||
    run.riskLevel === "CRITICAL" ||
    run.rtoFeasible === false ||
    run.emailState === "failed"
  );
}

/** Comma-separated addresses -> a list, or undefined when there are none. */
export function recipientsOf(text: string): string[] | undefined {
  const list = text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return list.length ? list : undefined;
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
