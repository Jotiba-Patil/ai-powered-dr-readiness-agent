import type { DependencyHealth } from "../api/types";
import { STATUS_TONES } from "../lib/labels";
import { Badge } from "./Badge";
import { Section } from "./Section";

export function DependencyTable({ dependencies }: { dependencies: DependencyHealth[] }) {
  const unhealthy = dependencies.filter((d) => d.actualStatus !== "UP").length;
  return (
    <Section title="Dependency health">
      {dependencies.length === 0 ? (
        <p className="text-sm text-slate-600">The runbook declares no dependencies.</p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-600">
            {unhealthy} of {dependencies.length} dependencies are not confirmed up.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-4">
                    Dependency
                  </th>
                  <th scope="col" className="py-2 pr-4">
                    Runbook assumes
                  </th>
                  <th scope="col" className="py-2 pr-4">
                    Actual status
                  </th>
                  <th scope="col" className="py-2">
                    Impact
                  </th>
                </tr>
              </thead>
              <tbody>
                {dependencies.map((dep) => (
                  <tr key={dep.name} className="border-b border-slate-100 last:border-0">
                    <th scope="row" className="py-2 pr-4 font-medium">
                      {dep.name}
                    </th>
                    <td className="py-2 pr-4">{dep.runbookAssumes}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={STATUS_TONES[dep.actualStatus]} />
                    </td>
                    <td className="py-2 text-slate-600">{dep.impact}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  );
}
