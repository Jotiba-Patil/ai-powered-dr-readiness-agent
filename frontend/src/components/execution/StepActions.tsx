import { useId, useState } from "react";
import type { StepRun } from "../../api/types";
import { isTerminalStep } from "../../lib/executionLabels";
import { CallEditor } from "./CallEditor";
import type { StepHandlers } from "./handlers";

function Action({
  label,
  onClick,
  disabled,
  primary = false,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  primary?: boolean;
}) {
  const style = primary
    ? "bg-ink-900 font-semibold text-white hover:bg-ink-700"
    : "border border-slate-300 bg-white hover:bg-slate-100";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-2 py-1 text-sm disabled:opacity-50 ${style}`}
    >
      {label}
    </button>
  );
}

/** The decisions that make sense in the step's state; the server re-checks every one. */
export function StepActions({
  step,
  handlers,
  disabled,
  locked,
}: {
  step: StepRun;
  handlers: StepHandlers;
  disabled: boolean;
  locked: boolean;
}) {
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  if (locked || isTerminalStep(step.state)) return null;

  const { state: s, call, rollback } = step;
  const needsHuman = s === "UNKNOWN" || (s === "VERIFYING" && !step.verify);
  const editable = ["AWAITING_APPROVAL", "PROPOSED", "REJECTED", "APPROVED"].includes(s);
  const decide = (action: Parameters<StepHandlers["decide"]>[1], succeeded?: boolean) => () =>
    handlers.decide(step, action, { reason, succeeded });
  const common = { disabled };

  if (editing) {
    return (
      <CallEditor
        call={call}
        onCancel={() => setEditing(false)}
        onSave={(next) => {
          setEditing(false);
          handlers.setCall(step, "main", next);
        }}
      />
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {s === "AWAITING_APPROVAL" && call && (
          <Action
            {...common}
            primary
            label="Approve"
            onClick={() => handlers.approve(step, "main", call.callHash)}
          />
        )}
        {s === "PROPOSED" && call && (
          <Action
            {...common}
            primary
            label="Accept proposal"
            onClick={() => handlers.setCall(step, "main", null)}
          />
        )}
        {editable && <Action {...common} label="Edit call" onClick={() => setEditing(true)} />}
        {s === "AWAITING_APPROVAL" && (
          <Action {...common} label="Reject" onClick={decide("reject")} />
        )}
        {(s === "PROPOSED" || s === "REJECTED") && (
          <Action {...common} label="Make manual" onClick={decide("manual")} />
        )}
        {s === "AWAITING_MANUAL" && (
          <Action {...common} primary label="Mark done" onClick={decide("mark-done")} />
        )}
        {needsHuman && (
          <>
            <Action
              {...common}
              primary
              label="Confirm it worked"
              onClick={decide("verify", true)}
            />
            <Action {...common} label="Report failure" onClick={decide("verify", false)} />
          </>
        )}
        {s === "FAILED" && <Action {...common} label="Retry" onClick={decide("retry")} />}
        {s === "FAILED" && rollback && (
          <>
            <Action
              {...common}
              label="Approve rollback"
              onClick={() => handlers.approve(step, "rollback", rollback.callHash)}
            />
            <Action {...common} primary label="Roll back" onClick={decide("rollback")} />
          </>
        )}
        <Action {...common} label="Skip" onClick={decide("skip")} />
      </div>
      <label htmlFor={reasonId} className="flex items-center gap-2 text-sm">
        Reason / note
        <input
          id={reasonId}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Needed to reject, skip or make manual"
          className="flex-1 rounded border border-slate-300 px-2 py-1"
        />
      </label>
    </div>
  );
}
