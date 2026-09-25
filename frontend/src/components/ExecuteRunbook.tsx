import { useId, useState } from "react";
import type { Api } from "../api/client";
import type { Report } from "../api/types";
import { ExecutionSection } from "./ExecutionSection";
import type { ExecutionStage } from "./JourneySteps";
import { Icon } from "./ui/Icon";

/** "Execute this runbook…" under a finished report; opens the execution section on request. */
export function ExecuteRunbook({
  api,
  jobId,
  report,
  pollIntervalMs,
  onStage,
}: {
  api: Api;
  jobId: string;
  report: Report;
  pollIntervalMs?: number;
  onStage?: (stage: ExecutionStage) => void;
}) {
  const [open, setOpen] = useState(false);
  const hintId = useId();
  if (open) {
    return (
      <ExecutionSection
        api={api}
        jobId={jobId}
        report={report}
        pollIntervalMs={pollIntervalMs}
        onStage={onStage}
      />
    );
  }
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label="Execute this runbook…"
      aria-describedby={hintId}
      className="card flex w-full items-center justify-between gap-3 p-5 text-left transition hover:ring-2 hover:ring-signal-400"
    >
      <span className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-white">
          <Icon name="play" />
        </span>
        <span>
          <span className="block font-semibold text-ink-900">Execute this runbook…</span>
          <span id={hintId} className="block text-sm text-slate-600">
            Dry run or live, following the plan above. Every tool call waits for approval.
          </span>
        </span>
      </span>
      <Icon name="arrow" className="h-5 w-5 text-slate-400" />
    </button>
  );
}
