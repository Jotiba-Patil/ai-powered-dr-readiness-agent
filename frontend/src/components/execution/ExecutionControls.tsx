import { useId, useState } from "react";
import type { Execution, LifecycleAction, StepState } from "../../api/types";
import { EXECUTION_TONES, TERMINAL_EXECUTION } from "../../lib/executionLabels";
import { Badge } from "../Badge";

/** Step states that still need someone's approval (or review) before the run can start. */
const UNAPPROVED: StepState[] = ["PLANNED", "PROPOSED", "AWAITING_APPROVAL", "REJECTED"];
const secondary = "btn-ghost";

/**
 * Run controls, kept in view above the steps (sticky). Start is enabled once every step is approved (manual and
 * skipped steps need no approval); Abort once the run has been started.
 */
export function ExecutionControls({
  execution,
  disabled,
  onLifecycle,
}: {
  execution: Execution;
  disabled: boolean;
  onLifecycle: (action: LifecycleAction, reason: string) => void;
}) {
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const state = execution.state;
  const act = (action: LifecycleAction) => () => onLifecycle(action, reason);

  if (TERMINAL_EXECUTION.includes(state)) {
    return (
      <section aria-label="Run controls" className="card p-4">
        <p className="flex items-center gap-2">
          This run is finished: <Badge tone={EXECUTION_TONES[state]} />
        </p>
      </section>
    );
  }

  const waiting = execution.steps.filter((step) => UNAPPROVED.includes(step.state));
  const started = state === "RUNNING" || state === "PAUSED";
  return (
    <section
      aria-label="Run controls"
      className="card sticky top-20 z-10 space-y-2 p-4 ring-1 ring-signal-400/30"
    >
      <div className="flex flex-wrap items-center gap-2">
        {state === "CREATED" && (
          <button
            type="button"
            className="btn-primary"
            disabled={disabled || waiting.length > 0}
            onClick={act("start")}
          >
            Start run
          </button>
        )}
        {state === "RUNNING" && (
          <button type="button" className={secondary} disabled={disabled} onClick={act("pause")}>
            Pause
          </button>
        )}
        {state === "PAUSED" && (
          <button type="button" className={secondary} disabled={disabled} onClick={act("resume")}>
            Resume
          </button>
        )}
        {started && (
          <button type="button" className={secondary} disabled={disabled} onClick={act("close")}>
            Close as failed
          </button>
        )}
        <button
          type="button"
          className="rounded-lg bg-red-700 px-4 py-2 font-semibold text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-45"
          disabled={disabled || !started}
          onClick={act("abort")}
        >
          Abort run
        </button>
        {started && (
          <label htmlFor={reasonId} className="flex items-center gap-2 text-sm">
            Reason
            <input
              id={reasonId}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Needed to pause, close or abort"
              className="rounded-lg border border-slate-300 px-2 py-1"
            />
          </label>
        )}
      </div>
      {state === "CREATED" && (
        <p className="text-sm text-slate-600">
          {waiting.length > 0
            ? `Approve every step to start: ${waiting.length} still waiting (step ${waiting.map((s) => s.stepNumber).join(", ")}).`
            : "All steps are approved. Start the run when ready."}
        </p>
      )}
    </section>
  );
}
