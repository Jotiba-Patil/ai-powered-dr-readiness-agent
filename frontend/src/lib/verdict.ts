// The report at a glance: one verdict sentence and a few key figures, all derived from the report.
import type { Report } from "../api/types";
import { minutes } from "./labels";

export type Mood = "good" | "watch" | "bad";

export interface Kpi {
  label: string;
  value: string;
  detail: string;
  mood: Mood;
  /** Section the tile jumps to. */
  anchor: string;
}

export const sectionAnchor = (title: string) =>
  `sec-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

export function verdict(report: Report): { headline: string; mood: Mood } {
  const { riskLevel } = report;
  const rto = report.rtoAnalysis;
  if (!rto.feasible) {
    return {
      headline: `Not ready: recovery takes ${minutes(rto.totalEstimatedMinutes)}, the RTO is ${minutes(rto.statedRtoMinutes)}.`,
      mood: "bad",
    };
  }
  if (riskLevel === "CRITICAL" || riskLevel === "HIGH") {
    return {
      headline: "Fits the RTO on paper, but serious gaps put recovery at risk.",
      mood: "bad",
    };
  }
  if (riskLevel === "MEDIUM") {
    return { headline: "Mostly ready: fix the flagged gaps before the next drill.", mood: "watch" };
  }
  return {
    headline: "Ready: this runbook should bring the service back within its RTO.",
    mood: "good",
  };
}

export function kpis(report: Report): Kpi[] {
  const rto = report.rtoAnalysis;
  const deps = report.dependencyHealth ?? [];
  const notUp = deps.filter((d) => d.actualStatus !== "UP").length;
  const gaps = report.gapAnalysis ?? [];
  const high = gaps.filter((g) => g.severity === "HIGH").length;
  const spofs = (report.singlePointsOfFailure ?? []).length;
  const history = report.historicalInsights;
  const tiles: Kpi[] = [
    {
      label: "Recovery time",
      value: `${minutes(rto.totalEstimatedMinutes)} / ${minutes(rto.statedRtoMinutes)}`,
      detail: rto.feasible
        ? `${minutes(rto.bufferMinutes)} to spare`
        : `${minutes(-rto.bufferMinutes)} over the RTO`,
      mood: rto.feasible
        ? rto.bufferMinutes < rto.statedRtoMinutes * 0.1
          ? "watch"
          : "good"
        : "bad",
      anchor: sectionAnchor("RTO feasibility"),
    },
    {
      label: "Dependencies",
      value: `${deps.length - notUp} of ${deps.length} up`,
      detail: notUp ? `${notUp} not confirmed up` : "all confirmed up",
      mood: notUp ? "bad" : "good",
      anchor: sectionAnchor("Dependency health"),
    },
    {
      label: "Gaps",
      value: String(gaps.length),
      detail: high ? `${high} high severity` : gaps.length ? "none high" : "none found",
      mood: high ? "bad" : gaps.length ? "watch" : "good",
      anchor: sectionAnchor("Gap analysis"),
    },
    {
      label: "Single points of failure",
      value: String(spofs),
      detail: spofs ? "people or systems with no backup" : "none identified",
      mood: spofs ? "watch" : "good",
      anchor: sectionAnchor("Single points of failure"),
    },
  ];
  if (history) {
    tiles.push({
      label: "Track record",
      value: `${history.liveRuns} live run${history.liveRuns === 1 ? "" : "s"}`,
      detail: `${history.analysesConsidered} earlier analysis(es)`,
      mood: "watch",
      anchor: sectionAnchor("Historical insights"),
    });
  }
  return tiles;
}
