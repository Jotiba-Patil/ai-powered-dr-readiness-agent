import type { ExecutionSummary } from "../../api/types";
import { EXECUTION_TONES } from "../../lib/executionLabels";
import { Badge } from "../Badge";

/** Earlier executions on this server, newest first. */
export function ExecutionList({
  executions,
  onOpen,
  onRefresh,
}: {
  executions: ExecutionSummary[];
  onOpen: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section
      aria-label="Runs of this analysis"
      className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">Runs of this analysis</h3>
        <button type="button" onClick={onRefresh} className="btn-ghost py-1 text-xs">
          Refresh
        </button>
      </div>
      {executions.length === 0 ? (
        <p className="text-sm text-slate-600">None yet.</p>
      ) : (
        <ul className="space-y-1">
          {executions.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => onOpen(item.id)}
                className="font-mono font-semibold text-signal-700 underline"
              >
                {item.id.slice(0, 8)}
              </button>
              <Badge tone={EXECUTION_TONES[item.state]} />
              <span>
                {item.runbookLabel} · {item.mode === "live" ? "live" : "dry run"} · {item.startedBy}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
