import type { Report } from "../api/types";
import { sectionAnchor } from "../lib/verdict";
import { DependencyTable } from "./DependencyTable";
import { GapList } from "./GapList";
import { HistoricalInsights } from "./HistoricalInsights";
import { ExecutionPlan, Suggestions } from "./PlanAndSuggestions";
import { VerdictHero } from "./report/VerdictHero";
import { RtoTimeline } from "./RtoTimeline";
import { SpofList } from "./SpofList";
import { Icon } from "./ui/Icon";

interface Props {
  report: Report;
  htmlUrl: string;
}

const JUMPS = [
  "RTO feasibility",
  "Dependency health",
  "Gap analysis",
  "Single points of failure",
  "Execution plan",
  "Suggestions",
];

/** Verdict first, then the evidence: timing, dependencies, risks, plan, and what history showed. */
export function ReportView({ report, htmlUrl }: Props) {
  const phases = report.executionPlan ?? [];
  const jumps = report.historicalInsights ? [...JUMPS, "Historical insights"] : JUMPS;
  return (
    <div className="space-y-5">
      {!report.aiAnalysisAvailable && (
        <div
          role="status"
          className="flex gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-900"
        >
          <Icon name="alert" className="mt-0.5 h-5 w-5" />
          <div>
            <p className="font-semibold">
              AI analysis unavailable: showing rule-based results only
            </p>
            {report.aiNote && <p className="text-sm">{report.aiNote}</p>}
          </div>
        </div>
      )}
      <VerdictHero report={report} htmlUrl={htmlUrl} />
      <nav aria-label="Report sections" className="flex flex-wrap gap-2 text-sm">
        {jumps.map((title) => (
          <a
            key={title}
            href={`#${sectionAnchor(title)}`}
            className="rounded-full bg-white px-3 py-1 text-slate-600 ring-1 ring-slate-200 hover:text-ink-900 hover:ring-signal-400"
          >
            {title}
          </a>
        ))}
      </nav>
      <RtoTimeline rto={report.rtoAnalysis} phases={phases} />
      <DependencyTable dependencies={report.dependencyHealth ?? []} />
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <GapList gaps={report.gapAnalysis ?? []} />
        <SpofList spofs={report.singlePointsOfFailure ?? []} />
      </div>
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <ExecutionPlan phases={phases} />
        <Suggestions suggestions={report.suggestions ?? []} />
      </div>
      {report.historicalInsights && <HistoricalInsights history={report.historicalInsights} />}
    </div>
  );
}
