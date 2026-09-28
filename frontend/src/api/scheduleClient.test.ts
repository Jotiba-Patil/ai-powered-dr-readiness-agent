import { describe, expect, it, vi } from "vitest";
import { ApiError, createApi } from "./client";

function recorder(body: unknown, status = 200) {
  const calls: string[] = [];
  const fetchImpl = vi.fn(async (input: Request) => {
    const text = input.method === "GET" || input.method === "DELETE" ? "" : await input.text();
    calls.push(`${input.method} ${input.url}${text ? ` ${text}` : ""}`);
    const noBody = status === 204;
    return new Response(noBody ? null : JSON.stringify(body), {
      status,
      headers: noBody ? {} : { "Content-Type": "application/json" },
    });
  });
  return { api: createApi("http://api.test", fetchImpl as unknown as typeof fetch), calls };
}

const BASE = "http://api.test/api/v1";

describe("schedule client", () => {
  it("reads schedules, runs and the scheduler state", async () => {
    const { api, calls } = recorder({ items: [], nextBefore: null });
    await api.listSchedules();
    await api.listScheduleRuns("s1");
    await api.listScheduleRuns("s1", "2026-09-27T06:00:00Z");
    await api.getScheduleRun("r1");
    await api.schedulerState();
    await api.previewRecipients("runbooks/a.md", ["x@example.com", "y@example.com"]);
    expect(calls).toEqual([
      `GET ${BASE}/schedules`,
      `GET ${BASE}/schedules/s1/runs?limit=20`,
      `GET ${BASE}/schedules/s1/runs?limit=20&before=2026-09-27T06%3A00%3A00Z`,
      `GET ${BASE}/schedule-runs/r1`,
      `GET ${BASE}/scheduler`,
      `GET ${BASE}/scheduler/recipient-preview?runbookPath=runbooks%2Fa.md&recipients=x%40example.com&recipients=y%40example.com`,
    ]);
  });

  it("sends changes with the person's name", async () => {
    const { api, calls } = recorder({});
    const spec = {
      name: "x",
      runbookPath: "runbooks/a.md",
      cadence: { kind: "hourly" as const, minute: 5 },
      timezone: "UTC",
    };
    await api.createSchedule({ ...spec, createdBy: "Bob" });
    await api.updateSchedule("s1", spec);
    await api.pauseSchedule("s1", "Bob", "2026-09-30T06:00:00.000Z");
    await api.pauseSchedule("s1", "Bob");
    await api.resumeSchedule("s1", "Bob");
    await api.runScheduleNow("s1");
    await api.cancelScheduleRun("r1");
    await api.pauseAll("Bob");
    await api.resumeAll("Bob");
    expect(calls).toEqual([
      `POST ${BASE}/schedules ${JSON.stringify({ ...spec, createdBy: "Bob" })}`,
      `PUT ${BASE}/schedules/s1 ${JSON.stringify(spec)}`,
      `POST ${BASE}/schedules/s1/pause {"by":"Bob","until":"2026-09-30T06:00:00.000Z"}`,
      `POST ${BASE}/schedules/s1/pause {"by":"Bob","until":null}`,
      `POST ${BASE}/schedules/s1/resume {"by":"Bob"}`,
      `POST ${BASE}/schedules/s1/run-now`,
      `POST ${BASE}/schedule-runs/r1/cancel`,
      `POST ${BASE}/scheduler/pause {"by":"Bob","until":null}`,
      `POST ${BASE}/scheduler/resume {"by":"Bob"}`,
    ]);
  });

  it("deletes with a 204 and reports errors with their code", async () => {
    const ok = recorder(null, 204);
    await expect(ok.api.deleteSchedule("s1")).resolves.toBeUndefined();
    expect(ok.calls).toEqual([`DELETE ${BASE}/schedules/s1`]);
    const missing = recorder({ error: "schedule s1 not found", code: "NOT_FOUND" }, 404);
    await expect(missing.api.deleteSchedule("s1")).rejects.toEqual(
      new ApiError("schedule s1 not found", "NOT_FOUND", 404),
    );
    const off = recorder({ error: "off", code: "SCHEDULER_DISABLED" }, 403);
    await expect(off.api.listSchedules()).rejects.toEqual(
      new ApiError("off", "SCHEDULER_DISABLED", 403),
    );
  });
});
