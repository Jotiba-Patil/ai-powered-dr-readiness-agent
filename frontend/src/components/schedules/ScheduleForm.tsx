import { useId, useState } from "react";
import type { Api } from "../../api/client";
import type { Cadence, CreateScheduleRequest } from "../../api/types";
import { useSamples } from "../../hooks/useSamples";
import { browserTimezone } from "../../lib/labels";
import { recipientsOf } from "../../lib/scheduleLabels";
import { CadenceFields } from "./CadenceFields";
import { FIELD, LABEL } from "./fieldStyles";
import { FormStep } from "./FormStep";
import { RunbookPicker } from "./RunbookPicker";
import { ScheduleSummary } from "./ScheduleSummary";
import { WhoIsTold } from "./WhoIsTold";

const INPUT = `w-full ${FIELD}`;
const DEFAULT_CADENCE: Cadence = { kind: "daily", time: "06:00" };

/**
 * A new schedule. The runbook comes from the server's folder or is uploaded; the timezone is the
 * browser's (not editable), so "06:00" means 06:00 where the schedule was created.
 */
export function ScheduleForm({
  api,
  createdBy,
  disabled,
  onCreate,
}: {
  api: Api;
  createdBy: string;
  disabled: boolean;
  /** Resolves true when the schedule was created; the form then resets every field. */
  onCreate: (body: CreateScheduleRequest) => Promise<boolean>;
}) {
  const ids = { name: useId(), inventory: useId() };
  const { samples, reload } = useSamples(api);
  const [timezone] = useState(browserTimezone);
  const [name, setName] = useState("");
  const [runbook, setRunbook] = useState("");
  const [inventory, setInventory] = useState("");
  const [cadence, setCadence] = useState<Cadence>(DEFAULT_CADENCE);
  const [recipients, setRecipients] = useState("");
  const [resets, setResets] = useState(0); // remounts the runbook picker, clearing its upload note
  const reset = () => {
    setName("");
    setRunbook("");
    setInventory("");
    setCadence(DEFAULT_CADENCE);
    setRecipients("");
    setResets((n) => n + 1);
  };
  const submit = async () => {
    const created = await onCreate({
      name: name.trim(),
      runbookPath: runbook,
      inventoryPath: inventory || null,
      cadence,
      timezone: timezone ?? "UTC",
      recipients: recipientsOf(recipients) ?? null,
      createdBy,
    });
    if (created) reset();
  };

  return (
    <form
      aria-label="New schedule"
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <FormStep
          step={1}
          title="What to check"
          hint="A runbook and, if you like, a health inventory."
        >
          <label htmlFor={ids.name} className="block text-sm">
            <span className={LABEL}>Name</span>
            <input
              id={ids.name}
              required
              maxLength={100}
              value={name}
              placeholder="e.g. Payments nightly check"
              onChange={(e) => setName(e.target.value)}
              className={INPUT}
            />
          </label>
          <RunbookPicker
            key={resets}
            api={api}
            runbooks={samples.runbooks}
            value={runbook}
            onChange={setRunbook}
            onUploaded={reload}
          />
          <label htmlFor={ids.inventory} className="block text-sm">
            <span className={LABEL}>Inventory (optional)</span>
            <select
              id={ids.inventory}
              value={inventory}
              onChange={(e) => setInventory(e.target.value)}
              className={INPUT}
            >
              <option value="">None</option>
              {samples.inventories.map((path) => (
                <option key={path} value={path}>
                  {path}
                </option>
              ))}
            </select>
          </label>
        </FormStep>
        <FormStep
          step={2}
          title="When"
          hint="Times are in your timezone; missed slots are skipped."
        >
          <CadenceFields cadence={cadence} onChange={setCadence} />
          <p className="text-sm text-slate-700" aria-label="Timezone">
            <span className={LABEL}>Timezone</span>
            <strong>{timezone ?? "UTC"}</strong>{" "}
            <span className="text-slate-500">
              {timezone ? "(from your browser)" : "(your browser reports none, so UTC is used)"}
            </span>
          </p>
        </FormStep>
        <WhoIsTold
          api={api}
          runbook={runbook}
          recipients={recipients}
          onRecipients={setRecipients}
        />
      </div>
      <ScheduleSummary
        name={name}
        runbook={runbook}
        cadence={cadence}
        timezone={timezone ?? "UTC"}
        disabled={disabled || !createdBy.trim()}
      />
    </form>
  );
}
