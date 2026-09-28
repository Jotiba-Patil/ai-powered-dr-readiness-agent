import { useId } from "react";
import type { Api } from "../../api/client";
import { recipientsOf } from "../../lib/scheduleLabels";
import { FIELD, LABEL } from "./fieldStyles";
import { FormStep } from "./FormStep";
import { RecipientLine } from "./RecipientLine";

/** Step 3: the runbook owner by default, or listed addresses; shows who would get the email. */
export function WhoIsTold({
  api,
  runbook,
  recipients,
  onRecipients,
}: {
  api: Api;
  runbook: string;
  recipients: string;
  onRecipients: (text: string) => void;
}) {
  const id = useId();
  return (
    <FormStep
      step={3}
      title="Who is told"
      hint="The runbook owner by default, from the contact directory."
    >
      <label htmlFor={id} className="block text-sm">
        <span className={LABEL}>
          Email instead of the runbook owner (optional, comma-separated)
        </span>
        <input
          id={id}
          value={recipients}
          placeholder="oncall@example.com"
          onChange={(e) => onRecipients(e.target.value)}
          className={`w-full ${FIELD}`}
        />
      </label>
      <div className="flex items-start gap-2 rounded-lg bg-white p-2 ring-1 ring-slate-200">
        <RecipientLine api={api} runbook={runbook} recipients={recipientsOf(recipients)} />
      </div>
    </FormStep>
  );
}
