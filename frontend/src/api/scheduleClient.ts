// Scheduled analysis endpoints (design scheduled-analysis section 9). The scheduler only
// analyzes; a run is executed with the existing `createExecution({ analysisJobId })`.
import type { Client } from "openapi-fetch";
import { call } from "./http";
import type { paths } from "./schema";
import type {
  CreateScheduleRequest,
  RecipientPreview,
  RunPage,
  ScheduleRun,
  ScheduleSpec,
  SchedulerView,
  ScheduleView,
} from "./types";

export function createScheduleApi(root: string, client: Client<paths>) {
  const id = (scheduleId: string) => ({ params: { path: { schedule_id: scheduleId } } });
  const run = (runId: string) => ({ params: { path: { run_id: runId } } });

  return {
    listSchedules(): Promise<ScheduleView[]> {
      return call(root, () => client.GET("/api/v1/schedules"));
    },

    createSchedule(body: CreateScheduleRequest): Promise<ScheduleView> {
      return call(root, () => client.POST("/api/v1/schedules", { body }));
    },

    updateSchedule(scheduleId: string, body: ScheduleSpec): Promise<ScheduleView> {
      return call(root, () =>
        client.PUT("/api/v1/schedules/{schedule_id}", { ...id(scheduleId), body }),
      );
    },

    /** 204 has no body, so success is reported as `true` to the shared error handling. */
    async deleteSchedule(scheduleId: string): Promise<void> {
      await call(root, async () => {
        const result = await client.DELETE("/api/v1/schedules/{schedule_id}", id(scheduleId));
        return { ...result, data: result.response.ok ? true : undefined };
      });
    },

    pauseSchedule(scheduleId: string, by: string, until?: string): Promise<ScheduleView> {
      return call(root, () =>
        client.POST("/api/v1/schedules/{schedule_id}/pause", {
          ...id(scheduleId),
          body: { by, until: until ?? null },
        }),
      );
    },

    resumeSchedule(scheduleId: string, by: string): Promise<ScheduleView> {
      return call(root, () =>
        client.POST("/api/v1/schedules/{schedule_id}/resume", { ...id(scheduleId), body: { by } }),
      );
    },

    runScheduleNow(scheduleId: string): Promise<ScheduleRun> {
      return call(root, () =>
        client.POST("/api/v1/schedules/{schedule_id}/run-now", id(scheduleId)),
      );
    },

    listScheduleRuns(scheduleId: string, before?: string): Promise<RunPage> {
      return call(root, () =>
        client.GET("/api/v1/schedules/{schedule_id}/runs", {
          params: { path: { schedule_id: scheduleId }, query: { limit: 20, before } },
        }),
      );
    },

    getScheduleRun(runId: string): Promise<ScheduleRun> {
      return call(root, () => client.GET("/api/v1/schedule-runs/{run_id}", run(runId)));
    },

    cancelScheduleRun(runId: string): Promise<ScheduleRun> {
      return call(root, () => client.POST("/api/v1/schedule-runs/{run_id}/cancel", run(runId)));
    },

    schedulerState(): Promise<SchedulerView> {
      return call(root, () => client.GET("/api/v1/scheduler"));
    },

    pauseAll(by: string, until?: string): Promise<SchedulerView> {
      return call(root, () =>
        client.POST("/api/v1/scheduler/pause", { body: { by, until: until ?? null } }),
      );
    },

    resumeAll(by: string): Promise<SchedulerView> {
      return call(root, () => client.POST("/api/v1/scheduler/resume", { body: { by } }));
    },

    previewRecipients(runbookPath: string, recipients?: string[]): Promise<RecipientPreview> {
      return call(root, () =>
        client.GET("/api/v1/scheduler/recipient-preview", {
          params: { query: { runbookPath, recipients } },
        }),
      );
    },
  };
}
