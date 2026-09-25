import type { SinglePointOfFailure } from "../api/types";
import { Section } from "./Section";

export function SpofList({ spofs }: { spofs: SinglePointOfFailure[] }) {
  return (
    <Section title="Single points of failure">
      {spofs.length === 0 ? (
        <p className="text-sm text-slate-600">No single points of failure identified.</p>
      ) : (
        <ul className="space-y-3">
          {spofs.map((spof, index) => {
            const steps = spof.affectedSteps ?? [];
            return (
              <li key={index} className="border-l-4 border-red-300 pl-3">
                <p>
                  <span aria-hidden="true">⚠ </span>
                  {spof.description}
                </p>
                {steps.length > 0 && (
                  <p className="text-sm text-slate-500">Affected steps: {steps.join(", ")}</p>
                )}
                <p className="text-sm text-slate-600">
                  <span className="font-medium">Mitigation:</span> {spof.mitigationSuggestion}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
