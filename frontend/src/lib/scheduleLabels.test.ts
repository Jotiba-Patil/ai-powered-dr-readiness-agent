import { describe, expect, it } from "vitest";
import { makeRun, makeSchedule } from "../test/scheduleFixtures";
import { browserTimezone } from "./labels";
import {
  emailResult,
  localInputToIso,
  parseScheduleHash,
  runResult,
  scheduleState,
} from "./scheduleLabels";

describe("scheduleLabels", () => {
  it("parses email links and ignores anything else", () => {
    expect(parseScheduleHash("#/schedules/s1/runs/r1")).toEqual({ scheduleId: "s1", runId: "r1" });
    expect(parseScheduleHash("#/schedules/s1/")).toEqual({ scheduleId: "s1", runId: null });
    expect(parseScheduleHash("")).toBeNull();
    expect(parseScheduleHash("#/schedules/<script>")).toBeNull();
    expect(parseScheduleHash("#/history/a1")).toBeNull();
  });

  it("describes schedule states", () => {
    expect(scheduleState(makeSchedule())).toBe("Active");
    expect(scheduleState(makeSchedule({ enabled: false, pausedBy: "Bob" }))).toBe("Paused by Bob");
    const until = makeSchedule({ enabled: false, pauseUntil: "2026-09-30T06:00:00Z" });
    expect(scheduleState(until)).toBe("Paused until 30 Sep 2026, 06:00 UTC");
  });

  it("describes run results and emails", () => {
    expect(runResult(makeRun({ rtoFeasible: true, riskLevel: "LOW", riskScore: 10 }))).toBe(
      "Risk 10 low · RTO feasible",
    );
    const bare = { riskScore: null, riskLevel: null } as const;
    expect(runResult(makeRun({ ...bare, state: "running" }))).toBe("Analyzing…");
    expect(runResult(makeRun({ ...bare, state: "cancelled" }))).toBe("Cancelled");
    expect(runResult(makeRun({ ...bare, state: "failed", errorCode: "PARSE_ERROR" }))).toBe(
      "Failed (PARSE_ERROR)",
    );
    expect(runResult(makeRun({ ...bare, state: "failed" }))).toBe("Failed");
    expect(emailResult(makeRun({ emailState: null }))).toBe("No email yet");
    expect(emailResult(makeRun({ emailState: "failed" }))).toBe("Email failed");
    expect(emailResult(makeRun({ emailState: "skipped" }))).toBe("No recipient");
  });

  it("converts local input times and finds the browser timezone", () => {
    expect(localInputToIso("")).toBeUndefined();
    expect(localInputToIso("not a date")).toBeUndefined();
    expect(localInputToIso("2026-09-30T08:00")).toBe(new Date("2026-09-30T08:00").toISOString());
    expect(browserTimezone()).toBe("UTC"); // pinned in vite.config.ts
  });
});
