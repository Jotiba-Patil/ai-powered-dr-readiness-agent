// How far a run is, grouped the way a person thinks about it: done, needs me, running, failed.
import type { Execution, StepRun, StepState } from "../api/types";

export type Bucket = "done" | "needsYou" | "running" | "failed" | "ready";

const NEEDS_YOU: StepState[] = ["PROPOSED", "AWAITING_APPROVAL", "REJECTED", "AWAITING_MANUAL"];

export function bucketOf(step: StepRun): Bucket {
  const s = step.state;
  if (s === "SUCCEEDED" || s === "MANUAL_DONE" || s === "SKIPPED") return "done";
  if (s === "FAILED" || s === "UNKNOWN" || s === "ROLLED_BACK") return "failed";
  if (s === "RUNNING" || (s === "VERIFYING" && step.verify != null)) return "running";
  if (NEEDS_YOU.includes(s) || s === "VERIFYING") return "needsYou";
  return "ready"; // PLANNED, APPROVED: waiting for the run or an earlier phase
}

export function runProgress(execution: Execution): Record<Bucket, number> & { total: number } {
  const counts = { done: 0, needsYou: 0, running: 0, failed: 0, ready: 0 };
  for (const step of execution.steps) counts[bucketOf(step)] += 1;
  return { ...counts, total: execution.steps.length };
}

/** Rail dot colours for the step timeline (the badge next to it carries the text). */
export const BUCKET_DOT: Record<Bucket, string> = {
  done: "bg-emerald-500 text-white ring-emerald-100",
  needsYou: "bg-amber-400 text-ink-900 ring-amber-100",
  running: "bg-signal-500 text-white ring-signal-300/40 animate-pulse",
  failed: "bg-red-500 text-white ring-red-100",
  ready: "bg-slate-300 text-slate-700 ring-slate-100",
};

export const BUCKET_BAR: Record<Bucket, string> = {
  done: "bg-emerald-500",
  needsYou: "bg-amber-400",
  running: "bg-signal-500",
  failed: "bg-red-500",
  ready: "bg-slate-200",
};

export const BUCKET_LABEL: Record<Bucket, string> = {
  done: "done",
  needsYou: "need you",
  running: "running",
  failed: "failed or rolled back",
  ready: "to do",
};
