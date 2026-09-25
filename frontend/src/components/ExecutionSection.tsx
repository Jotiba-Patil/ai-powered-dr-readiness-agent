import { useEffect, useId } from "react";
import type { Api } from "../api/client";
import type { ExecutionMode, Report } from "../api/types";
import { useExecution } from "../hooks/useExecution";
import { useExecutionCatalog } from "../hooks/useExecutionCatalog";
import { useStoredName } from "../hooks/useStoredName";
import { callingTools } from "../lib/executionLabels";
import { ExecutionList } from "./execution/ExecutionList";
import type { ExecutionStage } from "./JourneySteps";
import { ExecutionPanel } from "./execution/ExecutionPanel";
import { NewExecutionForm } from "./execution/NewExecutionForm";
import { ProgressNote } from "./execution/ProgressNote";
import { Section } from "./Section";
import { ErrorPanel } from "./StatusPanel";

const CREATE_HINT =
  "The server plans every step and checks each call against the policy. Steps without a " +
  "Tool: annotation get a call proposed by the AI, one step at a time, which can take a few " +
  "minutes with a local model.";

/** Execution of the analyzed runbook, shown under its report (it always follows an analysis). */
export function ExecutionSection({
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
  /** Tells the page whether a run of this analysis exists or has completed. */
  onStage?: (stage: ExecutionStage) => void;
}) {
  const nameId = useId();
  const catalog = useExecutionCatalog(api);
  const exec = useExecution(api, pollIntervalMs);
  const [name, setName] = useStoredName();
  const { settings, refresh } = catalog;
  const shownState = exec.execution?.state;
  const runs = catalog.executions.filter((item) => item.analysisJobId === jobId);
  const completedModes = runs.filter((run) => run.state === "COMPLETED").map((run) => run.mode);
  const stage: ExecutionStage =
    completedModes.length > 0 ? "done" : runs.length > 0 || exec.execution ? "started" : "none";

  useEffect(() => {
    onStage?.(stage);
  }, [stage, onStage]);

  // Keep the list's state badges in step with the execution on screen.
  useEffect(() => {
    if (shownState) void refresh();
  }, [shownState, refresh]);

  let body;
  if (catalog.error) {
    body = <p role="alert">Execution settings unavailable: {catalog.error}</p>;
  } else if (!settings) {
    body = <p role="status">Loading execution settings…</p>;
  } else if (!settings.enabled) {
    body = (
      <p role="status" className="text-sm text-slate-700">
        Runbook execution is turned off on this server. An operator enables it with{" "}
        <code>EXECUTION_ENABLED=true</code> (and <code>EXECUTION_ALLOW_LIVE=true</code> for live
        runs).
      </p>
    );
  } else {
    const create = (mode: ExecutionMode) => {
      // The run on screen is replaced by the new one; earlier runs stay in the list below.
      exec.clear();
      void exec.run(() => api.createExecution({ analysisJobId: jobId, mode, startedBy: name }), {
        label: `Creating the ${mode === "live" ? "live" : "dry"} run…`,
        hint: CREATE_HINT,
      });
    };
    body = (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-amber-50/70 p-3 ring-1 ring-amber-200">
          <label htmlFor={nameId} className="text-sm font-semibold text-ink-900">
            Your name
          </label>
          <input
            id={nameId}
            value={name}
            placeholder="Who is acting?"
            onChange={(event) => setName(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 shadow-sm"
          />
          <span className="text-sm text-amber-900">
            <span aria-hidden="true">⚠ </span>Identity not verified: approvals are recorded under
            the name you type. Destructive calls need {settings.approvalsByRisk.destructive ?? 2}{" "}
            different people.
          </span>
        </div>
        <NewExecutionForm
          report={report}
          allowLive={settings.allowLive}
          busy={exec.busy}
          startedBy={name}
          completedModes={completedModes}
          onCreate={create}
        />
        {exec.progress && <ProgressNote label={exec.progress.label} hint={exec.progress.hint} />}
        <ExecutionList
          executions={runs}
          onOpen={(id) => void exec.open(id)}
          onRefresh={() => void refresh()}
        />
        {exec.error && (
          <ErrorPanel title="Request refused" error={exec.error} onDismiss={exec.dismissError} />
        )}
        {!exec.busy && exec.execution && callingTools(exec.execution) && (
          <ProgressNote
            label="Run in progress: tool calls are running on the server"
            hint="This page updates by itself. Actions become available when a step needs a person."
          />
        )}
        {exec.execution && (
          <ExecutionPanel
            api={api}
            execution={exec.execution}
            settings={settings}
            name={name}
            busy={exec.busy}
            run={exec.run}
            history={report.historicalInsights?.steps ?? []}
          />
        )}
      </div>
    );
  }
  return <Section title="Execute this runbook">{body}</Section>;
}
