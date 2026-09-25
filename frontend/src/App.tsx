import { useState } from "react";
import type { Api } from "./api/client";
import { AnalyzeView } from "./components/AnalyzeView";
import { HistoryView } from "./components/history/HistoryView";
import { AppHeader, type View } from "./components/shell/AppHeader";
import { useServerStatus } from "./hooks/useServerStatus";

export function App({ api, pollIntervalMs }: { api: Api; pollIntervalMs?: number }) {
  const [view, setView] = useState<View>("analyze");
  const status = useServerStatus(api);
  return (
    <div className="min-h-screen">
      <AppHeader view={view} onView={setView} status={status} />
      {/* Both views stay mounted so a running analysis is not lost when switching. */}
      <main className="mx-auto max-w-6xl px-4 py-6">
        <div hidden={view !== "analyze"}>
          <AnalyzeView api={api} pollIntervalMs={pollIntervalMs} />
        </div>
        {view === "history" && <HistoryView api={api} />}
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-500">
        Recovery steps run only after named people approve them. Every decision is recorded in a
        tamper-evident audit log.
      </footer>
    </div>
  );
}
