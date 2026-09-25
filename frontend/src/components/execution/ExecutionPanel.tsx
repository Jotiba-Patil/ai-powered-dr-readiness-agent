import type { Api } from "../../api/client";
import type { Execution, ExecutionSettings, LifecycleAction, StepHistory } from "../../api/types";
import { useAudit } from "../../hooks/useAudit";
import type { RunAction } from "../../hooks/useExecution";
import { TERMINAL_EXECUTION } from "../../lib/executionLabels";
import { AuditPanel } from "./AuditPanel";
import { ExecutionControls } from "./ExecutionControls";
import { ExecutionHeader } from "./ExecutionHeader";
import type { StepHandlers } from "./handlers";
import { StepCard } from "./StepCard";

const LIFECYCLE_PROGRESS: Record<LifecycleAction, string> = {
  start: "Starting the run…",
  pause: "Pausing the run…",
  resume: "Resuming the run…",
  abort: "Aborting the run…",
  close: "Closing the run…",
};

/** One execution: header, steps by phase, run controls, audit log. Actions are sent as `name`. */
export function ExecutionPanel({
  api,
  execution,
  settings,
  name,
  busy,
  run,
  history = [],
}: {
  api: Api;
  execution: Execution;
  settings: ExecutionSettings;
  name: string;
  busy: boolean;
  run: RunAction;
  history?: StepHistory[];
}) {
  const { audit, error: auditError, load } = useAudit(api);
  const id = execution.id;
  const disabled = busy || !name.trim();
  const locked = TERMINAL_EXECUTION.includes(execution.state);

  const handlers: StepHandlers = {
    approve: (step, kind, callHash) =>
      void run(() => api.approveStep(id, step.stepNumber, { approver: name, callHash, kind }), {
        label: `Recording your approval of step ${step.stepNumber}…`,
      }),
    decide: (step, action, extra = {}) =>
      void run(
        () =>
          api.decideStep(id, step.stepNumber, action, {
            actor: name,
            reason: extra.reason?.trim() || null,
            succeeded: extra.succeeded ?? null,
          }),
        { label: `Sending "${action}" for step ${step.stepNumber}…` },
      ),
    setCall: (step, kind, call) =>
      void run(() => api.setCall(id, step.stepNumber, { editor: name, kind, call }), {
        label: `Saving the call of step ${step.stepNumber}…`,
      }),
  };
  const lifecycle = (action: LifecycleAction, reason: string) =>
    void run(
      () => api.changeExecution(id, action, { actor: name, reason: reason.trim() || null }),
      {
        label: LIFECYCLE_PROGRESS[action],
      },
    );

  const phases = [...new Set(execution.steps.map((step) => step.phase))].sort((a, b) => a - b);
  return (
    <div className="space-y-4" aria-label="Execution">
      <ExecutionHeader execution={execution} maxToolCalls={settings.maxToolCalls} />
      {!name.trim() && !locked && (
        <p role="note" className="rounded bg-amber-50 p-2 text-sm text-amber-900">
          <span aria-hidden="true">⚠ </span>Enter your name above to approve, complete or skip
          steps; the buttons stay disabled until then.
        </p>
      )}
      <ExecutionControls execution={execution} disabled={disabled} onLifecycle={lifecycle} />
      {phases.map((phase) => (
        <section key={phase} aria-label={`Phase ${phase}`} className="space-y-3">
          <h3 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
            Phase {phase}
          </h3>
          {execution.steps
            .filter((step) => step.phase === phase)
            .map((step) => (
              <StepCard
                key={step.stepNumber}
                step={step}
                approvalsByRisk={settings.approvalsByRisk}
                handlers={handlers}
                disabled={disabled}
                locked={locked}
                past={history.find((past) => past.stepNumber === step.stepNumber)}
              />
            ))}
        </section>
      ))}
      <AuditPanel audit={audit} error={auditError} onLoad={() => void load(id)} />
    </div>
  );
}
