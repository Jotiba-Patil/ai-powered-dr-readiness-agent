import { useState, type FormEvent } from "react";
import type { AnalyzeRequest, SampleList, SystemInventory } from "../api/types";
import { SamplePicker } from "./SamplePicker";
import { Icon } from "./ui/Icon";
import { TextSource } from "./TextSource";

interface Props {
  samples: SampleList;
  samplesError: string | null;
  loadSample: (path: string) => Promise<string>;
  busy: boolean;
  onAnalyze: (request: AnalyzeRequest) => void;
}

/** Runbook + optional inventory input. The server validates both; this only checks JSON syntax. */
export function InputPanel({ samples, samplesError, loadSample, busy, onAnalyze }: Props) {
  const [runbook, setRunbook] = useState("");
  const [runbookName, setRunbookName] = useState<string | undefined>();
  const [inventory, setInventory] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const pick = async (kind: "runbook" | "inventory", path: string) => {
    if (!path) return;
    try {
      const text = await loadSample(path);
      setProblem(null);
      if (kind === "runbook") {
        setRunbook(text);
        setRunbookName(path.split("/").pop());
      } else {
        setInventory(text);
      }
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Could not load the sample");
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!runbook.trim()) {
      setProblem("Paste, upload or pick a runbook first.");
      return;
    }
    let parsed: SystemInventory | undefined;
    if (inventory.trim()) {
      try {
        parsed = JSON.parse(inventory) as SystemInventory;
      } catch {
        setProblem("The inventory is not valid JSON.");
        return;
      }
    }
    setProblem(null);
    onAnalyze({
      runbookMarkdown: runbook,
      inventory: parsed ?? null,
      runbookName: runbookName ?? null,
    });
  };

  return (
    <form onSubmit={submit} aria-label="Analysis input" className="card space-y-4 p-5">
      <div>
        <h2 className="text-lg font-semibold text-ink-900">Which runbook should we check?</h2>
        <p className="text-sm text-slate-600">
          Start from a sample or paste your own Markdown. Add an inventory to check that every
          dependency is actually up; without one, dependencies are reported as unverified.
        </p>
      </div>
      <SamplePicker
        samples={samples}
        error={samplesError}
        disabled={busy}
        onPick={(kind, path) => void pick(kind, path)}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <TextSource
          label="Runbook (Markdown)"
          value={runbook}
          onChange={(value) => {
            setRunbook(value);
            setRunbookName(undefined);
          }}
          accept=".md,.markdown,text/markdown,text/plain"
          placeholder="# Service Name&#10;**Owner:** ...&#10;## Recovery Steps"
        />
        <TextSource
          label="Inventory (JSON, optional)"
          value={inventory}
          onChange={setInventory}
          accept=".json,application/json"
          placeholder='{ "services": [ ... ] }'
        />
      </div>
      {problem && (
        <p role="alert" className="text-sm text-red-700">
          <span aria-hidden="true">✖ </span>
          {problem}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="btn-primary inline-flex items-center gap-2 px-5 py-2.5"
      >
        <Icon name="pulse" />
        {busy ? "Analyzing…" : "Analyze runbook"}
      </button>
    </form>
  );
}
