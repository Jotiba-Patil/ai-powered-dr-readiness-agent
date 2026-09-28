// Visual vocabulary for levels and statuses. Color is never the only signal: every entry has an icon
// and a text label that components render alongside the color.
import type { DependencyStatus, RiskLevel, Severity, StepHistory } from "../api/types";

export interface Tone {
  icon: string;
  label: string;
  className: string;
  color: string;
}

export const RISK_TONES: Record<RiskLevel, Tone> = {
  LOW: { icon: "✔", label: "Low", className: "bg-emerald-100 text-emerald-800", color: "#059669" },
  MEDIUM: {
    icon: "●",
    label: "Medium",
    className: "bg-amber-100 text-amber-800",
    color: "#d97706",
  },
  HIGH: { icon: "▲", label: "High", className: "bg-orange-100 text-orange-800", color: "#ea580c" },
  CRITICAL: {
    icon: "✖",
    label: "Critical",
    className: "bg-red-100 text-red-800",
    color: "#dc2626",
  },
};

export const SEVERITY_TONES: Record<Severity, Tone> = {
  LOW: { icon: "●", label: "Low", className: "bg-sky-100 text-sky-800", color: "#0284c7" },
  MEDIUM: {
    icon: "▲",
    label: "Medium",
    className: "bg-amber-100 text-amber-800",
    color: "#d97706",
  },
  HIGH: { icon: "✖", label: "High", className: "bg-red-100 text-red-800", color: "#dc2626" },
};

export const STATUS_TONES: Record<DependencyStatus, Tone> = {
  UP: { icon: "✔", label: "Up", className: "bg-emerald-100 text-emerald-800", color: "#059669" },
  DOWN: { icon: "✖", label: "Down", className: "bg-red-100 text-red-800", color: "#dc2626" },
  UNREACHABLE: {
    icon: "?",
    label: "Unreachable",
    className: "bg-orange-100 text-orange-800",
    color: "#ea580c",
  },
  NOT_IN_INVENTORY: {
    icon: "—",
    label: "Not in inventory",
    className: "bg-slate-200 text-slate-700",
    color: "#64748b",
  },
};

export const SEVERITIES: Severity[] = ["HIGH", "MEDIUM", "LOW"];

export function humanize(value: string): string {
  const text = value.toLowerCase().replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function minutes(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} min`;
}

/** The browser's IANA timezone, e.g. "Asia/Calcutta"; `null` if the browser reports none. */
export function browserTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The one way a time is shown (design scheduled-analysis 18.4): the server sends UTC and people
 * see their own time, e.g. "28 Sep 2026, 11:30 UTC+05:30". Same text as the backend's
 * `display_time()`; `timeZone` defaults to the browser's.
 */
export function formatDateTime(
  iso: string,
  options: { timeZone?: string; seconds?: boolean } = {},
): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: options.timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: options.seconds ? "2-digit" : undefined,
    hourCycle: "h23",
    timeZoneName: "longOffset",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  const offset = part("timeZoneName").replace(/^GMT/, "");
  const zone = !offset || /^[+-]00:00$/.test(offset) ? "UTC" : `UTC${offset}`;
  const clock = `${part("hour")}:${part("minute")}${options.seconds ? `:${part("second")}` : ""}`;
  const month = MONTHS[Number(part("month")) - 1] ?? "";
  return `${Number(part("day"))} ${month} ${part("year")}, ${clock} ${zone}`;
}

/** One line per execution step: what past live runs of it showed (information only). */
export function previousRuns(past: StepHistory): string {
  const median = past.medianActiveMinutes;
  const timing = median == null ? "" : `, median ${minutes(median)}`;
  return `Previous live runs: ${past.liveRuns}, failed ${past.failed ?? 0}, rolled back ${past.rolledBack ?? 0}${timing}`;
}
