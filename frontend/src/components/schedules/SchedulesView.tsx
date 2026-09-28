import { useEffect, useState } from "react";
import type { Api } from "../../api/client";
import { useSchedules } from "../../hooks/useSchedules";
import { useStoredName } from "../../hooks/useStoredName";
import { clearScheduleHash, type ScheduleLink } from "../../lib/scheduleLabels";
import { Section } from "../Section";
import { ScheduleForm } from "./ScheduleForm";
import { ScheduleList, type ScheduleActions } from "./ScheduleList";
import { ScheduleRuns } from "./ScheduleRuns";
import { ScheduledRunDetail } from "./ScheduledRunDetail";
import { SchedulerBar } from "./SchedulerBar";
import { YourName } from "./YourName";

interface OpenRun {
  analysisId: string;
  scheduleId: string;
}

/** Scheduled analyses: list, create, pause, runs, and a run's report with execution. */
export function SchedulesView({
  api,
  link,
  pollIntervalMs,
}: {
  api: Api;
  link?: ScheduleLink | null;
  pollIntervalMs?: number;
}) {
  const [name, setName] = useStoredName();
  const data = useSchedules(api);
  const [openSchedule, setOpenSchedule] = useState<string | null>(link?.scheduleId ?? null);
  const [openRun, setOpenRun] = useState<OpenRun | null>(null);
  const by = name.trim();
  const canAct = by !== "" && data.pending === null;

  useEffect(() => {
    if (!link?.runId) return; // an email link: open that run's report
    let active = true;
    api.getScheduleRun(link.runId).then(
      (run) =>
        active &&
        run.analysisId &&
        setOpenRun({ analysisId: run.analysisId, scheduleId: run.scheduleId }),
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, [api, link?.runId]);

  if (openRun) {
    return (
      <ScheduledRunDetail
        key={openRun.analysisId}
        api={api}
        analysisId={openRun.analysisId}
        scheduleName={
          data.schedules.find((s) => s.id === openRun.scheduleId)?.name ?? "this schedule"
        }
        pollIntervalMs={pollIntervalMs}
        onBack={() => {
          setOpenRun(null);
          clearScheduleHash();
        }}
      />
    );
  }
  if (data.status === "loading") return <p role="status">Loading schedules…</p>;
  if (data.status === "disabled") {
    return (
      <p role="status" className="card p-4 text-sm text-slate-700">
        Scheduled analysis is turned off on this server (<code>SCHEDULER_ENABLED=false</code>).
      </p>
    );
  }
  if (data.status === "error" || !data.scheduler) {
    return <p role="alert">Schedules unavailable: {data.error}</p>;
  }

  const byId = (id: string) => data.schedules.find((s) => s.id === id);
  const actions: ScheduleActions = {
    open: setOpenSchedule,
    runNow: (id) => {
      void data.act("Starting a run…", () => api.runScheduleNow(id));
      setOpenSchedule(id);
    },
    pause: (id, until) => void data.act("Pausing…", () => api.pauseSchedule(id, by, until)),
    resume: (id) => void data.act("Resuming…", () => api.resumeSchedule(id, by)),
    remove: (id) => {
      if (!window.confirm(`Delete schedule "${byId(id)?.name}"? Its analyses stay in History.`))
        return;
      if (openSchedule === id) setOpenSchedule(null);
      void data.act("Deleting…", () => api.deleteSchedule(id));
    },
  };
  const shown = openSchedule ? byId(openSchedule) : undefined;

  return (
    <div className="space-y-5">
      <Section
        title="Schedules"
        actions={
          <button type="button" className="btn-ghost" onClick={() => void data.refresh()}>
            Refresh
          </button>
        }
      >
        <div className="space-y-3">
          <YourName name={name} onName={setName} />
          <SchedulerBar
            scheduler={data.scheduler}
            canAct={canAct}
            onPauseAll={(until) => void data.act("Pausing all…", () => api.pauseAll(by, until))}
            onResumeAll={() => void data.act("Resuming all…", () => api.resumeAll(by))}
          />
          {data.pending && <p role="status">{data.pending}</p>}
          {data.actionError && <p role="alert">{data.actionError}</p>}
          <ScheduleList
            schedules={data.schedules}
            actions={actions}
            canAct={canAct}
            maxPauseDays={data.scheduler.maxPauseDays}
          />
        </div>
      </Section>
      {shown && (
        <ScheduleRuns
          key={shown.id}
          api={api}
          schedule={shown}
          pollIntervalMs={pollIntervalMs}
          canAct={canAct}
          onOpenRun={(_runId, analysisId) => setOpenRun({ analysisId, scheduleId: shown.id })}
          onCancel={(runId) => data.act("Cancelling the run…", () => api.cancelScheduleRun(runId))}
          onClose={() => setOpenSchedule(null)}
        />
      )}
      <Section title="New schedule">
        <ScheduleForm
          api={api}
          createdBy={by}
          disabled={!canAct}
          onCreate={(body) => data.act("Creating the schedule…", () => api.createSchedule(body))}
        />
      </Section>
    </div>
  );
}
