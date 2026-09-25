import type { ExecutionMode, Report } from "../../api/types";
import { Icon } from "../ui/Icon";

const WARN_LEVELS = ["HIGH", "CRITICAL"];

interface Option {
  mode: ExecutionMode;
  title: string;
  blurb: string;
  button: string;
  className: string;
  done: boolean;
  blocked: string | null;
}

/** Starts a dry or live run of the runbook this report analyzed: two clearly different choices. */
export function NewExecutionForm({
  report,
  allowLive,
  busy,
  startedBy,
  completedModes,
  onCreate,
}: {
  report: Report;
  allowLive: boolean;
  busy: boolean;
  startedBy: string;
  /** Modes that already have a completed run for this analysis: their button is disabled. */
  completedModes: ExecutionMode[];
  onCreate: (mode: ExecutionMode) => void;
}) {
  const risky = WARN_LEVELS.includes(report.riskLevel);
  const noName = !startedBy.trim();
  const options: Option[] = [
    {
      mode: "dry_run",
      title: "Dry run",
      blurb: "Rehearse: every call is planned, checked and approved, but nothing is changed.",
      button: "Create dry run",
      className: "btn-primary",
      done: completedModes.includes("dry_run"),
      blocked: null,
    },
    {
      mode: "live",
      title: "Live run",
      blurb: "Recover for real: approved calls run against the MCP servers, one at a time.",
      button: "Create live run",
      className:
        "rounded-lg bg-red-700 px-4 py-2 font-semibold text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-45",
      done: completedModes.includes("live"),
      blocked: allowLive ? null : "Live runs are off on this server.",
    },
  ];
  return (
    <div className="space-y-3" aria-label="New execution">
      <p className="text-sm text-slate-700">
        Runs <strong>{report.meta.runbookFile}</strong> step by step, following the execution plan
        above. Every tool call needs approval; a dry run calls nothing.
      </p>
      {risky && (
        <p
          role="note"
          className="flex gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-200"
        >
          <Icon name="alert" className="mt-0.5 h-4 w-4" />
          <span>
            The analysis rated this runbook {report.riskLevel} risk ({report.riskScore}). Review the
            gaps before a live run.
          </span>
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {options.map((option) => (
          <div
            key={option.mode}
            className={`flex flex-col gap-3 rounded-xl p-4 ring-1 ${
              option.mode === "live" ? "bg-red-50/40 ring-red-200" : "bg-slate-50 ring-slate-200"
            }`}
          >
            <div>
              <p className="font-semibold text-ink-900">{option.title}</p>
              <p className="text-sm text-slate-600">{option.blurb}</p>
            </div>
            <div className="mt-auto flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy || noName || option.done || option.blocked !== null}
                onClick={() => onCreate(option.mode)}
                className={option.className}
              >
                {option.button}
              </button>
              {option.done && (
                <span className="flex items-center gap-1 text-sm text-emerald-800">
                  <Icon name="check" />
                  {option.title} completed.
                </span>
              )}
              {option.blocked && <span className="text-sm text-slate-600">{option.blocked}</span>}
            </div>
          </div>
        ))}
      </div>
      {noName && <p className="text-sm text-slate-600">Enter your name first.</p>}
    </div>
  );
}
