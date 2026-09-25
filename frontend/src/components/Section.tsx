import type { ReactNode } from "react";
import { sectionAnchor } from "../lib/verdict";
import { Icon, type IconName } from "./ui/Icon";

const ICONS: Record<string, IconName> = {
  "RTO feasibility": "clock",
  "Dependency health": "database",
  "Single points of failure": "users",
  "Gap analysis": "alert",
  "Execution plan": "route",
  Suggestions: "lightbulb",
  "Historical insights": "history",
  "Execute this runbook": "play",
  "Stored analyses": "history",
  "Executions of this analysis": "list",
};

/** A titled card; the heading labels the region, and the id is a jump target from the verdict. */
export function Section({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const headingId = `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const icon = ICONS[title];
  return (
    <section id={sectionAnchor(title)} aria-labelledby={headingId} className="card p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="flex items-center gap-2 text-lg font-semibold text-ink-900">
          {icon && (
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-signal-500/10 text-signal-700">
              <Icon name={icon} />
            </span>
          )}
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
