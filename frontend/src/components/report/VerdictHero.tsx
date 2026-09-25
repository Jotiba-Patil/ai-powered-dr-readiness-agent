import type { Report } from "../../api/types";
import { downloadText, slug } from "../../lib/download";
import { minutes } from "../../lib/labels";
import { kpis, verdict, type Mood } from "../../lib/verdict";
import { RiskGauge } from "../RiskGauge";
import { Icon } from "../ui/Icon";

const MOOD = {
  good: { ring: "ring-emerald-200 bg-emerald-50/60", text: "text-emerald-800", icon: "check" },
  watch: { ring: "ring-amber-200 bg-amber-50/60", text: "text-amber-800", icon: "alert" },
  bad: { ring: "ring-red-200 bg-red-50/60", text: "text-red-800", icon: "alert" },
} as const satisfies Record<Mood, { ring: string; text: string; icon: "check" | "alert" }>;

const BAND = { good: "from-emerald-500", watch: "from-amber-400", bad: "from-red-500" };

/** Executive summary: the verdict first, then the few numbers that decide it, then the prose. */
export function VerdictHero({ report, htmlUrl }: { report: Report; htmlUrl: string }) {
  const service = report.serviceSummary;
  const { headline, mood } = verdict(report);
  const exportJson = () =>
    downloadText(
      `dr-report-${slug(service.name)}.json`,
      JSON.stringify(report, null, 2),
      "application/json",
    );
  return (
    <section aria-labelledby="section-executive-summary" className="card overflow-hidden">
      <div aria-hidden="true" className={`h-1.5 bg-gradient-to-r ${BAND[mood]} to-transparent`} />
      <div className="grid gap-6 p-5 md:grid-cols-[auto_1fr]">
        <RiskGauge score={report.riskScore} level={report.riskLevel} />
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2
                id="section-executive-summary"
                className="text-xs font-semibold tracking-wider text-slate-500 uppercase"
              >
                Executive summary
              </h2>
              <h3 className="text-2xl font-semibold text-ink-900">{service.name}</h3>
              <p className="text-sm text-slate-600">
                Owner {service.owner} · RTO {minutes(service.statedRTO)} · RPO{" "}
                {minutes(service.statedRPO)} · analyzed{" "}
                {new Date(report.meta.analyzedAt).toLocaleString()} in{" "}
                {(report.meta.analysisTimeMs / 1000).toFixed(1)} s
              </p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={exportJson} className="btn-ghost">
                Export JSON
              </button>
              <a href={htmlUrl} download className="btn-ghost">
                Export HTML
              </a>
            </div>
          </div>
          <p className={`flex items-start gap-2 text-lg font-medium ${MOOD[mood].text}`}>
            <Icon name={MOOD[mood].icon} className="mt-1 h-5 w-5" />
            {headline}
          </p>
        </div>
      </div>
      <ul className="grid gap-3 border-t border-slate-100 bg-slate-50/60 p-4 sm:grid-cols-2 lg:grid-cols-5">
        {kpis(report).map((kpi) => (
          <li key={kpi.label}>
            <a
              href={`#${kpi.anchor}`}
              className={`block h-full rounded-xl p-3 ring-1 transition hover:-translate-y-0.5 hover:shadow-sm ${MOOD[kpi.mood].ring}`}
            >
              <span className="text-xs font-medium text-slate-500">{kpi.label}</span>
              <span className="tabular block text-xl font-semibold text-ink-900">{kpi.value}</span>
              <span className={`flex items-center gap-1 text-xs ${MOOD[kpi.mood].text}`}>
                <Icon name={MOOD[kpi.mood].icon} className="h-3.5 w-3.5" />
                {kpi.detail}
              </span>
            </a>
          </li>
        ))}
      </ul>
      <div className="flex gap-3 p-5">
        <Icon
          name={report.aiAnalysisAvailable ? "sparkles" : "file"}
          className="mt-1 h-4 w-4 text-signal-600"
        />
        <p className="max-w-3xl leading-relaxed whitespace-pre-line text-slate-700">
          {report.summary}
        </p>
      </div>
    </section>
  );
}
