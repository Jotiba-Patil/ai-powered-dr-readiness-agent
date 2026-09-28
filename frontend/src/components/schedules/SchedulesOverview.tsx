import type { ReactNode } from "react";
import { sectionAnchor } from "../../lib/verdict";
import { Icon } from "../ui/Icon";

/** Jumps to the "New schedule" form and puts the cursor in its first field. */
function toForm(): void {
  const form = document.getElementById(sectionAnchor("New schedule"));
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.querySelector("input")?.focus({ preventScroll: true });
}

/** The Schedules card: a status band (signal while running, amber while paused) and the header. */
export function SchedulesOverview({
  paused,
  onRefresh,
  children,
}: {
  paused: boolean;
  onRefresh: () => void;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby="section-schedules" className="card overflow-hidden">
      <div
        aria-hidden="true"
        className={`h-1.5 bg-gradient-to-r ${paused ? "from-amber-400" : "from-signal-500"} to-transparent`}
      />
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-signal-300 shadow-sm">
              <Icon name="calendar" className="h-5 w-5" />
            </span>
            <div>
              <h2 id="section-schedules" className="text-xl font-semibold text-ink-900">
                Schedules
              </h2>
              <p className="text-sm text-slate-600">
                Recurring readiness checks: analyze a runbook on a timetable and email the owner.
              </p>
            </div>
          </div>
          <span className="flex gap-2">
            <button
              type="button"
              className="btn-ghost inline-flex items-center gap-1.5"
              onClick={onRefresh}
            >
              <Icon name="refresh" className="h-3.5 w-3.5" />
              Refresh
            </button>
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-1.5 py-1.5 text-sm"
              onClick={toForm}
            >
              <Icon name="plus" />
              Add schedule
            </button>
          </span>
        </div>
        {children}
      </div>
    </section>
  );
}
