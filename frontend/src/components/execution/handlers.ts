import type { PlannedToolCall, StepAction, StepRun } from "../../api/types";

/** What a step card can ask for; ExecutionPanel turns these into API calls under the user's name. */
export interface StepHandlers {
  approve: (step: StepRun, kind: "main" | "rollback", callHash: string) => void;
  decide: (
    step: StepRun,
    action: StepAction,
    extra?: { reason?: string; succeeded?: boolean },
  ) => void;
  setCall: (
    step: StepRun,
    kind: "main" | "verify" | "rollback",
    call: PlannedToolCall | null,
  ) => void;
}
