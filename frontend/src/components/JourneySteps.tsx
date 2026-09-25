import { Icon } from "./ui/Icon";

/** How far execution got for the report on screen (reported by the execution section). */
export type ExecutionStage = "none" | "started" | "done";

const STEPS = [
  { title: "Runbook", hint: "Pick, paste or upload" },
  { title: "Readiness report", hint: "Rules + AI check it" },
  { title: "Execution", hint: "Optional, approved step by step" },
];

/** Where the user is in the flow: runbook -> report -> (optional) execution. */
export function JourneySteps({
  current,
  execution = "none",
}: {
  current: 0 | 1 | 2;
  execution?: ExecutionStage;
}) {
  return (
    <ol aria-label="Progress" className="grid gap-2 sm:grid-cols-3">
      {STEPS.map((step, index) => {
        const finished = index === 2 && execution === "done";
        const done = index < current || finished;
        const active = index === current && !finished;
        const hint = index === 2 && execution === "started" ? "Run in progress" : step.hint;
        return (
          <li
            key={step.title}
            aria-current={active ? "step" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3 py-2 ring-1 ${
              active
                ? "bg-white ring-signal-400 shadow-sm"
                : done
                  ? "bg-white/60 ring-emerald-200"
                  : "bg-white/40 ring-slate-200"
            }`}
          >
            <span
              className={`grid h-7 w-7 place-items-center rounded-full text-sm font-semibold ${
                done
                  ? "bg-emerald-500 text-white"
                  : active
                    ? "bg-ink-900 text-white"
                    : "bg-slate-200 text-slate-600"
              }`}
            >
              {done ? <Icon name="check" /> : index + 1}
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold text-ink-900">{step.title}</span>
              <span className="text-xs text-slate-500">{done ? "Done" : hint}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
