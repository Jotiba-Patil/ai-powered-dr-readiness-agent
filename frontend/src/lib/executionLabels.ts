// Visual vocabulary for executions: every tone has an icon and a label, never color alone.
import type {
  CallSource,
  Execution,
  ExecutionState,
  RiskClass,
  StepState,
  ToolCall,
} from "../api/types";
import type { Tone } from "./labels";

const tone = (icon: string, label: string, className: string, color: string): Tone => ({
  icon,
  label,
  className,
  color,
});
const WAIT = "bg-amber-100 text-amber-900";
const GOOD = "bg-emerald-100 text-emerald-800";
const BAD = "bg-red-100 text-red-800";
const INFO = "bg-sky-100 text-sky-800";
const IDLE = "bg-slate-200 text-slate-700";

export const STEP_TONES: Record<StepState, Tone> = {
  PLANNED: tone("○", "Planned", IDLE, "#64748b"),
  PROPOSED: tone("?", "Needs review", WAIT, "#d97706"),
  AWAITING_APPROVAL: tone("✋", "Awaiting approval", WAIT, "#d97706"),
  APPROVED: tone("✔", "Approved", INFO, "#0284c7"),
  REJECTED: tone("✖", "Rejected", BAD, "#dc2626"),
  RUNNING: tone("▶", "Running", INFO, "#0284c7"),
  VERIFYING: tone("…", "Verifying", INFO, "#0284c7"),
  SUCCEEDED: tone("✔", "Succeeded", GOOD, "#059669"),
  FAILED: tone("✖", "Failed", BAD, "#dc2626"),
  UNKNOWN: tone("?", "Outcome unknown", BAD, "#dc2626"),
  ROLLED_BACK: tone("↺", "Rolled back", IDLE, "#64748b"),
  AWAITING_MANUAL: tone("✋", "Manual step", WAIT, "#d97706"),
  MANUAL_DONE: tone("✔", "Done by hand", GOOD, "#059669"),
  SKIPPED: tone("»", "Skipped", IDLE, "#64748b"),
};

export const EXECUTION_TONES: Record<ExecutionState, Tone> = {
  CREATED: tone("○", "Created", IDLE, "#64748b"),
  RUNNING: tone("▶", "Running", INFO, "#0284c7"),
  PAUSED: tone("❚❚", "Paused", WAIT, "#d97706"),
  COMPLETED: tone("✔", "Completed", GOOD, "#059669"),
  FAILED: tone("✖", "Failed", BAD, "#dc2626"),
  ABORTED: tone("■", "Aborted", BAD, "#dc2626"),
};

export const RISK_CLASS_TONES: Record<RiskClass, Tone> = {
  read: tone("◎", "Read", INFO, "#0284c7"),
  write: tone("✎", "Write", WAIT, "#d97706"),
  destructive: tone("⚠", "Destructive", BAD, "#dc2626"),
};

export const SOURCE_LABELS: Record<CallSource, string> = {
  annotated: "Annotated",
  ai_proposed: "AI-proposed",
  edited: "Edited",
};

export const TERMINAL_EXECUTION: ExecutionState[] = ["COMPLETED", "FAILED", "ABORTED"];
const TERMINAL_STEP: StepState[] = ["SUCCEEDED", "MANUAL_DONE", "SKIPPED", "ROLLED_BACK"];

export const isTerminalStep = (state: StepState) => TERMINAL_STEP.includes(state);

/** Approvals a call needs, from the server's `approvalsByRisk` (0 when it failed policy). */
export function approvalsNeeded(call: ToolCall, byRisk: Record<string, number>): number {
  return call.riskClass ? (byRisk[call.riskClass] ?? 1) : 0;
}

export const shortHash = (hash: string) => (hash ? `${hash.slice(0, 12)}…` : "—");

/** The server is calling tools right now (not waiting for a person). */
export const callingTools = (execution: Execution) =>
  execution.state === "RUNNING" &&
  execution.steps.some(
    (step) => step.state === "RUNNING" || (step.state === "VERIFYING" && step.verify != null),
  );
