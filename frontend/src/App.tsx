import { useEffect, useState } from "react";
import type { Api } from "./api/client";
import { AnalyzeView } from "./components/AnalyzeView";
import { HistoryView } from "./components/history/HistoryView";
import { SchedulesView } from "./components/schedules/SchedulesView";
import { AppHeader, type View } from "./components/shell/AppHeader";
import { useServerStatus } from "./hooks/useServerStatus";
import { parseScheduleHash } from "./lib/scheduleLabels";

export function App({ api, pollIntervalMs }: { api: Api; pollIntervalMs?: number }) {
  // Links in scheduled-run emails open #/schedules/{id}/runs/{runId} (no router needed),
  // on first load and when the hash changes in an already open tab.
  const [link, setLink] = useState(() => parseScheduleHash(window.location.hash));
  const [view, setView] = useState<View>(link ? "schedules" : "analyze");
  const status = useServerStatus(api);

  useEffect(() => {
    const follow = () => {
      const next = parseScheduleHash(window.location.hash);
      if (!next) return;
      setLink(next);
      setView("schedules");
    };
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, []);

  return (
    <div className="min-h-screen">
      <AppHeader view={view} onView={setView} status={status} />
      {/* Both views stay mounted so a running analysis is not lost when switching. */}
      <main className="mx-auto max-w-6xl px-4 py-6">
        <div hidden={view !== "analyze"}>
          <AnalyzeView api={api} pollIntervalMs={pollIntervalMs} />
        </div>
        {view === "history" && <HistoryView api={api} />}
        {view === "schedules" && (
          <SchedulesView
            key={link ? `${link.scheduleId}/${link.runId ?? ""}` : "list"}
            api={api}
            link={link}
            pollIntervalMs={pollIntervalMs}
          />
        )}
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-500">
        Recovery steps run only after named people approve them. Every decision is recorded in a
        tamper-evident audit log.
      </footer>
    </div>
  );
}
