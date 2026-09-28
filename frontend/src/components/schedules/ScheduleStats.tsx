import type { SchedulerView, ScheduleView } from "../../api/types";
import { formatDateTime } from "../../lib/labels";
import { needsAttention, relativeTime } from "../../lib/scheduleLabels";
import { Icon, type IconName } from "../ui/Icon";

type Mood = "good" | "watch" | "bad" | "calm";

const MOOD: Record<Mood, { ring: string; text: string }> = {
  good: { ring: "ring-emerald-200 bg-emerald-50/60", text: "text-emerald-800" },
  watch: { ring: "ring-amber-200 bg-amber-50/60", text: "text-amber-800" },
  bad: { ring: "ring-red-200 bg-red-50/60", text: "text-red-800" },
  calm: { ring: "ring-slate-200 bg-white", text: "text-slate-600" },
};

interface Tile {
  label: string;
  value: string;
  detail: string;
  icon: IconName;
  mood: Mood;
}

function tiles(scheduler: SchedulerView, schedules: ScheduleView[]): Tile[] {
  const active = schedules.filter((s) => s.enabled).length;
  const paused = schedules.length - active;
  const upcoming = scheduler.paused
    ? []
    : schedules
        .filter((s) => s.enabled && s.nextRunAt)
        .sort((a, b) => Date.parse(a.nextRunAt ?? "") - Date.parse(b.nextRunAt ?? ""));
  const next = upcoming[0];
  const attention = schedules.filter(needsAttention).length;
  return [
    {
      label: "Active schedules",
      value: `${active} of ${schedules.length}`,
      detail: paused ? `${paused} paused` : `Up to ${scheduler.maxSchedules} allowed`,
      icon: "clock",
      mood: paused ? "watch" : "calm",
    },
    {
      label: "Next run",
      value: next?.nextRunAt ? relativeTime(next.nextRunAt) : "None planned",
      detail: next?.nextRunAt
        ? `${next.name} · ${formatDateTime(next.nextRunAt)}`
        : scheduler.paused
          ? "Everything is paused"
          : "No active schedule",
      icon: "calendar",
      mood: next ? "calm" : "watch",
    },
    {
      label: "Needs attention",
      value: String(attention),
      detail: attention ? "Failed, high risk or RTO not feasible" : "Last runs look fine",
      icon: attention ? "alert" : "check",
      mood: attention ? "bad" : "good",
    },
    {
      label: "Emails",
      value: scheduler.emailTransport === "smtp" ? "SMTP" : "Log only",
      detail: scheduler.allowedDomains.length
        ? `To ${scheduler.allowedDomains.join(", ")}`
        : "Any domain",
      icon: "mail",
      mood: "calm",
    },
  ];
}

/** Four at-a-glance numbers for the schedules, in the report's KPI-tile style. */
export function ScheduleStats({
  scheduler,
  schedules,
}: {
  scheduler: SchedulerView;
  schedules: ScheduleView[];
}) {
  return (
    <ul aria-label="Schedule overview" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {tiles(scheduler, schedules).map((tile) => (
        <li key={tile.label} className={`rounded-xl p-3 ring-1 ${MOOD[tile.mood].ring}`}>
          <span className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
            <Icon name={tile.icon} className="h-3.5 w-3.5" />
            {tile.label}
          </span>
          <span className="tabular block text-xl font-semibold text-ink-900">{tile.value}</span>
          <span className={`block truncate text-xs ${MOOD[tile.mood].text}`} title={tile.detail}>
            {tile.detail}
          </span>
        </li>
      ))}
    </ul>
  );
}
