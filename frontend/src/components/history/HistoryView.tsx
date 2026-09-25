import { useState } from "react";
import type { Api } from "../../api/client";
import { useHistory } from "../../hooks/useHistory";
import { Section } from "../Section";
import { AnalysisList } from "./AnalysisList";
import { HistoryDetail } from "./HistoryDetail";

/** Stored analyses; opening one shows its report and its executions (ADR 0007). */
export function HistoryView({ api }: { api: Api }) {
  const history = useHistory(api);
  const [open, setOpen] = useState<string | null>(null);

  if (open) {
    const back = () => {
      setOpen(null);
      history.refresh(); // execution counts may have changed
    };
    return <HistoryDetail key={open} api={api} analysisId={open} onBack={back} />;
  }

  let body;
  if (history.status === "loading") {
    body = <p role="status">Loading history…</p>;
  } else if (history.status === "disabled") {
    body = (
      <p role="status" className="text-sm text-slate-700">
        Analysis history is turned off on this server (<code>HISTORY_ENABLED=false</code>).
      </p>
    );
  } else if (history.status === "error") {
    body = <p role="alert">History unavailable: {history.error}</p>;
  } else {
    body = (
      <AnalysisList
        items={history.items}
        filters={history.filters}
        onFilters={history.setFilters}
        hasMore={history.next !== null}
        onMore={history.loadMore}
        onOpen={setOpen}
      />
    );
  }
  return (
    <Section
      title="Stored analyses"
      actions={
        <button type="button" onClick={history.refresh} className="btn-ghost">
          Refresh
        </button>
      }
    >
      {body}
    </Section>
  );
}
