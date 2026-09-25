import { useState } from "react";
import type { Gap, Severity } from "../api/types";
import { SEVERITIES, SEVERITY_TONES, humanize } from "../lib/labels";
import { Badge } from "./Badge";
import { Section } from "./Section";

/** Gap analysis with a severity filter (toggle buttons, all on by default). */
export function GapList({ gaps }: { gaps: Gap[] }) {
  const [shown, setShown] = useState<Set<Severity>>(() => new Set(SEVERITIES));
  const toggle = (severity: Severity) =>
    setShown((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  const visible = gaps.filter((gap) => shown.has(gap.severity));

  const filter = (
    <div role="group" aria-label="Filter gaps by severity" className="flex gap-1">
      {SEVERITIES.map((severity) => {
        const count = gaps.filter((g) => g.severity === severity).length;
        return (
          <button
            key={severity}
            type="button"
            aria-pressed={shown.has(severity)}
            onClick={() => toggle(severity)}
            className="rounded border border-slate-300 px-2 py-0.5 text-xs aria-pressed:bg-slate-800 aria-pressed:text-white"
          >
            {SEVERITY_TONES[severity].label} ({count})
          </button>
        );
      })}
    </div>
  );

  return (
    <Section title="Gap analysis" actions={gaps.length > 0 ? filter : undefined}>
      {gaps.length === 0 ? (
        <p className="text-sm text-slate-600">No gaps found.</p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-slate-600">No gaps match the selected severities.</p>
      ) : (
        <ul className="space-y-3">
          {visible.map((gap, index) => (
            <li key={`${gap.type}-${index}`} className="border-l-4 border-slate-200 pl-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={SEVERITY_TONES[gap.severity]} />
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {humanize(gap.type)}
                </span>
              </div>
              <p className="mt-1">{gap.description}</p>
              <p className="text-sm text-slate-600">
                <span className="font-medium">Recommendation:</span> {gap.recommendation}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
