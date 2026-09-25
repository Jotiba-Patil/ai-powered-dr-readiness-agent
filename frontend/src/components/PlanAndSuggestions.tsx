import type { ExecutionPhase, Suggestion } from "../api/types";
import { minutes } from "../lib/labels";
import { Section } from "./Section";

export function ExecutionPlan({ phases }: { phases: ExecutionPhase[] }) {
  return (
    <Section title="Execution plan">
      {phases.length === 0 ? (
        <p className="text-sm text-slate-600">No recovery steps to plan.</p>
      ) : (
        <ol className="space-y-3">
          {phases.map((phase) => (
            <li key={phase.phase} className="rounded border border-slate-200 p-3">
              <p className="font-semibold">
                Phase {phase.phase}: step{phase.steps.length === 1 ? "" : "s"}{" "}
                {phase.steps.join(", ")}
                {phase.steps.length > 1 && (
                  <span className="font-normal text-slate-500"> (in parallel)</span>
                )}
              </p>
              <p className="text-sm text-slate-600">
                {minutes(phase.estimatedMinutes)} · Gate: {phase.gate}
              </p>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

export function Suggestions({ suggestions }: { suggestions: Suggestion[] }) {
  const sorted = [...suggestions].sort((a, b) => a.priority - b.priority);
  return (
    <Section title="Suggestions">
      {sorted.length === 0 ? (
        <p className="text-sm text-slate-600">No suggestions.</p>
      ) : (
        <ul className="space-y-3">
          {sorted.map((suggestion, index) => (
            <li key={index}>
              <p className="font-semibold">
                <span className="mr-2 rounded bg-ink-900 px-1.5 text-xs font-semibold text-white">
                  P{suggestion.priority}
                </span>
                {suggestion.title}
              </p>
              <p className="text-sm text-slate-600">{suggestion.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
