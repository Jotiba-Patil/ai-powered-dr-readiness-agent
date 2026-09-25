import type { StepHistory, StepRun } from "../../api/types";
import { STEP_TONES } from "../../lib/executionLabels";
import { BUCKET_DOT, bucketOf } from "../../lib/runProgress";
import { minutes, previousRuns } from "../../lib/labels";
import { Badge } from "../Badge";
import { CallView } from "./CallView";
import type { StepHandlers } from "./handlers";
import { StepActions } from "./StepActions";

/** One runbook step: its state, the calls it would make, and what a person can decide now. */
export function StepCard({
  step,
  approvalsByRisk,
  handlers,
  disabled,
  locked,
  past,
}: {
  step: StepRun;
  approvalsByRisk: Record<string, number>;
  handlers: StepHandlers;
  disabled: boolean;
  locked: boolean;
  /** Past live runs of this step, from the report's historical insights. */
  past?: StepHistory;
}) {
  const calls = [step.call, step.verify, step.rollback].filter((c) => c != null);
  return (
    <article aria-label={`Step ${step.stepNumber}`} className="relative pl-11">
      <span
        aria-hidden="true"
        className="absolute top-9 bottom-[-0.75rem] left-[15px] w-px bg-slate-200"
      />
      <span
        aria-hidden="true"
        className={`tabular absolute top-2 left-0 grid h-8 w-8 place-items-center rounded-full text-sm font-semibold ring-4 ${BUCKET_DOT[bucketOf(step)]}`}
      >
        {step.stepNumber}
      </span>
      <div className="card space-y-2 p-4">
        <header className="flex flex-wrap items-center gap-2">
          <h4 className="font-semibold text-ink-900">
            <span className="sr-only">{step.stepNumber}. </span>
            {step.action}
          </h4>
          <Badge tone={STEP_TONES[step.state]} />
          {step.attempt > 1 && (
            <span className="text-xs text-slate-600">attempt {step.attempt}</span>
          )}
        </header>
        <p className="text-sm text-slate-600">
          Owner {step.owner} · {minutes(step.estimatedMinutes)}
          {(step.dependsOn ?? []).length > 0 &&
            ` · after step ${(step.dependsOn ?? []).join(", ")}`}
        </p>
        {past && <p className="text-sm text-slate-500">{previousRuns(past)}</p>}
        {step.summary && <p className="text-sm">{step.summary}</p>}
        {(step.policyErrors ?? []).map((problem) => (
          <p key={problem} className="text-sm text-red-800">
            <span aria-hidden="true">✖ </span>
            {problem}
          </p>
        ))}
        {step.proposal && (
          <p className="text-sm text-slate-700">
            <span className="font-semibold">AI rationale (not verified): </span>
            {step.proposal.rationale}
            {step.proposal.confidence && ` (confidence ${step.proposal.confidence})`}
          </p>
        )}
        {calls.map((call) => (
          <CallView key={call.kind} call={call} approvalsByRisk={approvalsByRisk} />
        ))}
        <StepActions step={step} handlers={handlers} disabled={disabled} locked={locked} />
      </div>
    </article>
  );
}
