import { useCallback, useEffect, useRef, useState } from "react";
import type { Api } from "../api/client";
import { useAnalysis } from "../hooks/useAnalysis";
import { useSamples } from "../hooks/useSamples";
import { ExecuteRunbook } from "./ExecuteRunbook";
import { InputPanel } from "./InputPanel";
import { JourneySteps, type ExecutionStage } from "./JourneySteps";
import { ReportView } from "./ReportView";
import { ErrorPanel, LoadingPanel } from "./StatusPanel";
import { Icon } from "./ui/Icon";

/** Input, job progress, report and, when the user asks for it, execution of that runbook. */
export function AnalyzeView({ api, pollIntervalMs }: { api: Api; pollIntervalMs?: number }) {
  const { state, analyze, reset } = useAnalysis(api, pollIntervalMs);
  const { samples, error: samplesError, load } = useSamples(api);
  const busy = state.phase === "submitting" || state.phase === "running";
  const done = state.phase === "done";
  const resultRef = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<ExecutionStage>("none");
  const [inputKey, setInputKey] = useState(0); // a new key gives empty editors
  const onStage = useCallback((next: ExecutionStage) => setStage(next), []);

  /** "Analyze another runbook": back to step 1 with an empty input, no report, no run. */
  const startOver = () => {
    reset();
    setStage("none");
    setInputKey((key) => key + 1);
  };

  useEffect(() => {
    if (done) resultRef.current?.focus();
  }, [done]);

  return (
    <div className="space-y-5">
      <JourneySteps current={done ? 2 : busy ? 1 : 0} execution={done ? stage : "none"} />
      {done && (
        <div className="card flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <p className="flex items-center gap-2 text-sm text-slate-700">
            <Icon name="file" className="h-4 w-4 text-signal-600" />
            Report for{" "}
            <strong>{sourceLabel(state.report.meta.runbookFile, "pasted runbook")}</strong>
            {state.report.meta.inventoryFile === "(none)"
              ? " without an inventory"
              : ` checked against ${sourceLabel(state.report.meta.inventoryFile, "the pasted inventory")}`}
          </p>
          <button type="button" onClick={startOver} className="btn-ghost">
            Analyze another runbook
          </button>
        </div>
      )}
      <div hidden={done}>
        <InputPanel
          key={inputKey}
          samples={samples}
          samplesError={samplesError}
          loadSample={load}
          busy={busy}
          onAnalyze={(request) => {
            setStage("none");
            void analyze(request);
          }}
        />
      </div>
      {busy && <LoadingPanel jobId={state.phase === "running" ? state.jobId : null} />}
      {state.phase === "error" && <ErrorPanel error={state.error} onDismiss={reset} />}
      {done && (
        <>
          <SavedNote saved={state.historySaved} />
          <div ref={resultRef} tabIndex={-1} aria-label="Readiness report" className="outline-none">
            <ReportView report={state.report} htmlUrl={api.reportHtmlUrl(state.jobId)} />
          </div>
          <ExecuteRunbook
            key={state.jobId}
            api={api}
            jobId={state.jobId}
            report={state.report}
            pollIntervalMs={pollIntervalMs}
            onStage={onStage}
          />
        </>
      )}
    </div>
  );
}

function SavedNote({ saved }: { saved: boolean | null }) {
  if (saved === null) return null;
  return saved ? (
    <p role="status" className="flex items-center gap-1.5 text-sm text-slate-500">
      <Icon name="check" className="h-4 w-4 text-emerald-600" />
      Saved to history.
    </p>
  ) : (
    <p role="status" className="flex items-center gap-1.5 text-sm text-amber-800">
      <Icon name="alert" className="h-4 w-4" />
      Not saved to history (the server could not store it). The report is still shown here.
    </p>
  );
}

/** The server labels pasted text "request-body.*"; say what it means instead. */
function sourceLabel(label: string, pasted: string): string {
  return label.startsWith("request-body.") ? pasted : label;
}
