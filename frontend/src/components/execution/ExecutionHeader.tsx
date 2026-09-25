import type { Execution } from "../../api/types";
import { EXECUTION_TONES, shortHash } from "../../lib/executionLabels";
import { Badge } from "../Badge";
import { RunProgress } from "./RunProgress";

/** Runbook, mode, state, audit head and pause reason. The run controls sit below the steps. */
export function ExecutionHeader({
  execution,
  maxToolCalls,
}: {
  execution: Execution;
  /** Unknown when shown from the history with execution off. */
  maxToolCalls?: number;
}) {
  const live = execution.mode === "live";
  return (
    <header className="card overflow-hidden">
      <div
        aria-hidden="true"
        className={`h-1.5 ${live ? "bg-gradient-to-r from-red-600 to-orange-400" : "bg-gradient-to-r from-ink-700 to-slate-400"}`}
      />
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-semibold text-ink-900">{execution.runbookLabel}</h3>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-bold tracking-wide ${live ? "bg-red-600 text-white" : "bg-ink-800 text-white"}`}
          >
            {live ? "LIVE" : "DRY RUN"}
          </span>
          <Badge tone={EXECUTION_TONES[execution.state]} />
        </div>
        <p className="tabular text-xs text-slate-500">
          Started by {execution.startedBy} · tool calls {execution.toolCallsUsed}
          {maxToolCalls !== undefined && `/${maxToolCalls}`} · audit head{" "}
          <code>{shortHash(execution.auditHead)}</code> · id {execution.id}
        </p>
        {execution.pauseReason && (
          <p className="text-sm font-semibold text-amber-900">Paused: {execution.pauseReason}</p>
        )}
        <RunProgress execution={execution} />
      </div>
    </header>
  );
}
