import type { ServiceHistory } from "../api/types";
import { minutes, utcMinute } from "../lib/labels";
import { Section } from "./Section";

/** What past analyses and live runs of this service showed (measured by the server, ADR 0009). */
export function HistoricalInsights({ history }: { history: ServiceHistory }) {
  const steps = history.steps ?? [];
  const runs = history.executions ?? [];
  const unhealthy = (history.dependencies ?? []).filter(
    (d) => (d.down ?? 0) + (d.unreachable ?? 0) > 0,
  );
  return (
    <Section title="Historical insights">
      <p className="text-sm text-slate-700">
        {history.liveRuns} live run(s) and {history.analysesConsidered} earlier analysis(es) of this
        service. {history.dryRuns} dry run(s) are counted but not measured.
      </p>
      {steps.length > 0 && (
        <table className="mt-3 w-full text-left text-sm">
          <caption className="sr-only">Past live runs per step</caption>
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-1">Step</th>
              <th>Live runs</th>
              <th>Succeeded</th>
              <th>Failed</th>
              <th>Rolled back</th>
              <th>Median time</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((step) => {
              const measured = step.medianActiveMinutes;
              const slow = measured != null && measured > step.estimatedMinutes * 1.5;
              return (
                <tr key={step.stepNumber} className="border-b border-slate-100">
                  <th scope="row" className="py-1 font-normal">
                    {step.stepNumber}
                  </th>
                  <td>{step.liveRuns}</td>
                  <td>{step.succeeded ?? 0}</td>
                  <td>{step.failed ?? 0}</td>
                  <td>{step.rolledBack ?? 0}</td>
                  <td className={slow ? "font-semibold text-orange-800" : undefined}>
                    {measured == null
                      ? "—"
                      : `${minutes(measured)} (estimate ${minutes(step.estimatedMinutes)})`}
                    {slow && <span className="sr-only"> (over estimate)</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {runs.length > 0 && (
        <div className="mt-3">
          <h3 className="text-sm font-semibold">Recent live runs</h3>
          <ul className="text-sm">
            {runs.map((run) => (
              <li key={run.executionId}>
                {utcMinute(run.startedAt)}: {run.state} in {minutes(run.elapsedMinutes)}
                {run.elapsedMinutes > run.statedRtoMinutes &&
                  ` (over the ${minutes(run.statedRtoMinutes)} RTO)`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {unhealthy.length > 0 && (
        <div className="mt-3">
          <h3 className="text-sm font-semibold">Dependencies that were not up</h3>
          <ul className="text-sm">
            {unhealthy.map((dep) => (
              <li key={dep.name}>
                {dep.name}: down or unreachable in {(dep.down ?? 0) + (dep.unreachable ?? 0)} of{" "}
                {dep.analyses} analyses
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
