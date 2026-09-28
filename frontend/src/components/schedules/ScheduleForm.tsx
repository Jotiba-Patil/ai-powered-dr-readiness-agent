import { useId, useState } from "react";
import type { Api } from "../../api/client";
import type { Cadence, CreateScheduleRequest } from "../../api/types";
import { useSamples } from "../../hooks/useSamples";
import { browserTimezone } from "../../lib/labels";
import { CadenceFields } from "./CadenceFields";
import { RecipientLine } from "./RecipientLine";
import { RunbookPicker } from "./RunbookPicker";

const INPUT = "w-full rounded-md border border-slate-300 px-2 py-1";
const DEFAULT_CADENCE: Cadence = { kind: "daily", time: "06:00" };

function recipientsOf(text: string): string[] | undefined {
  const list = text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return list.length ? list : undefined;
}

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
  const ids = { name: useId(), inventory: useId(), to: useId() };
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
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <label htmlFor={ids.name} className="text-sm">
        <span className="block text-slate-700">Name</span>
        <input
          id={ids.name}
          required
          maxLength={100}
          value={name}
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
      <label htmlFor={ids.inventory} className="text-sm">
        <span className="block text-slate-700">Inventory (optional)</span>
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
      <p className="text-sm text-slate-700" aria-label="Timezone">
        <span className="block">Timezone</span>
        <strong>{timezone ?? "UTC"}</strong>{" "}
        <span className="text-slate-500">
          {timezone ? "(from your browser)" : "(your browser reports none, so UTC is used)"}
        </span>
      </p>
      <div className="sm:col-span-2">
        <CadenceFields cadence={cadence} onChange={setCadence} />
      </div>
      <label htmlFor={ids.to} className="text-sm sm:col-span-2">
        <span className="block text-slate-700">
          Email instead of the runbook owner (optional, comma-separated)
        </span>
        <input
          id={ids.to}
          value={recipients}
          onChange={(e) => setRecipients(e.target.value)}
          className={INPUT}
        />
      </label>
      <div className="sm:col-span-2">
        <RecipientLine api={api} runbook={runbook} recipients={recipientsOf(recipients)} />
      </div>
      <div className="sm:col-span-2">
        <button type="submit" className="btn-primary" disabled={disabled || !createdBy.trim()}>
          Create schedule
        </button>
        <span className="ml-3 text-xs text-slate-500">
          Scheduled runs only analyze and email; running the recovery always needs a person.
        </span>
      </div>
    </form>
  );
}
