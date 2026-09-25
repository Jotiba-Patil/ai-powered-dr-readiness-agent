import type { Api } from "../../api/client";
import type { StoredExecution } from "../../api/types";
import { usePastExecutions } from "../../hooks/usePastExecutions";
import { AuditPanel } from "../execution/AuditPanel";
import { ExecutionHeader } from "../execution/ExecutionHeader";
import { ExecutionList } from "../execution/ExecutionList";
import type { StepHandlers } from "../execution/handlers";
import { StepCard } from "../execution/StepCard";
import { Section } from "../Section";

// Read-only: the cards are locked, so no action can be taken from the history.
const NO_ACTIONS: StepHandlers = {
  approve: () => undefined,
  decide: () => undefined,
  setCall: () => undefined,
};

/** What happened when this analysis was executed: its runs, their steps and audit logs. */
export function PastExecutions({ api, analysisId }: { api: Api; analysisId: string }) {
  const past = usePastExecutions(api, analysisId);
  let body;
  if (past.runs === null && !past.error) {
    body = <p role="status">Loading executions…</p>;
  } else {
    body = (
      <div className="space-y-4">
        <p className="text-sm text-slate-600">
          Read-only record of past runs. To run this runbook again, analyze it on the Analyze tab so
          the run follows current dependency health.
        </p>
        {past.error && <p role="alert">{past.error}</p>}
        {past.runs && (
          <ExecutionList executions={past.runs} onOpen={past.open} onRefresh={past.refresh} />
        )}
        {past.selected && (
          <ExecutionDetail
            stored={past.selected}
            maxToolCalls={past.settings?.maxToolCalls}
            approvalsByRisk={past.settings?.approvalsByRisk ?? {}}
            onRefresh={past.refresh}
            onClose={past.close}
          />
        )}
      </div>
    );
  }
  return <Section title="Executions of this analysis">{body}</Section>;
}

function ExecutionDetail({
  stored,
  maxToolCalls,
  approvalsByRisk,
  onRefresh,
  onClose,
}: {
  stored: StoredExecution;
  maxToolCalls?: number;
  approvalsByRisk: Record<string, number>;
  onRefresh: () => void;
  onClose: () => void;
}) {
  const { execution, audit } = stored;
  const phases = [...new Set(execution.steps.map((step) => step.phase))].sort((a, b) => a - b);
  return (
    <div className="space-y-4" aria-label="Execution details">
      <button type="button" onClick={onClose} className="btn-ghost">
        Close details
      </button>
      <ExecutionHeader execution={execution} maxToolCalls={maxToolCalls} />
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
                approvalsByRisk={approvalsByRisk}
                handlers={NO_ACTIONS}
                disabled
                locked
              />
            ))}
        </section>
      ))}
      <AuditPanel audit={audit} error={null} onLoad={onRefresh} />
    </div>
  );
}
