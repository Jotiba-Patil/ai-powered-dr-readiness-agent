import { describe, expect, it } from "vitest";
import { makeRun, makeSchedule } from "../test/scheduleFixtures";
import { browserTimezone } from "./labels";
import {
  cadenceSentence,
  emailResult,
  localInputToIso,
  needsAttention,
  parseScheduleHash,
  recipientsOf,
  relativeTime,
  runDuration,
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

  it("describes a cadence in plain words", () => {
    expect(cadenceSentence({ kind: "hourly", minute: 5 }, "UTC")).toBe(
      "Every hour at 05 minutes past",
    );
    expect(cadenceSentence({ kind: "daily", time: "06:00" }, "UTC")).toBe(
      "Every day at 06:00 (UTC)",
    );
    expect(
      cadenceSentence({ kind: "weekly", weekday: "mon", time: "07:30" }, "Asia/Calcutta"),
    ).toBe("Every Monday at 07:30 (Asia/Calcutta)");
    expect(cadenceSentence({ kind: "monthly", day: 15, time: "01:00" }, "UTC")).toBe(
      "On day 15 of every month at 01:00 (UTC)",
    );
    expect(cadenceSentence({ kind: "monthly", day: "last", time: "01:00" }, "UTC")).toBe(
      "On the last day of every month at 01:00 (UTC)",
    );
  });

  it("gives relative times and run durations", () => {
    const now = Date.parse("2026-09-28T06:00:00Z");
    expect(relativeTime("2026-09-28T06:25:00Z", now)).toBe("in 25 min");
    expect(relativeTime("2026-09-28T03:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-09-30T06:00:00Z", now)).toBe("in 2 days");
    expect(relativeTime("2026-09-28T06:00:10Z", now)).toBe("in under a minute");
    expect(relativeTime("2026-09-28T05:59:50Z", now)).toBe("just now");
    expect(relativeTime("nope", now)).toBe("");
    expect(runDuration(makeRun())).toBe("2 min");
    expect(runDuration(makeRun({ finishedAt: "2026-09-27T06:00:45Z" }))).toBe("45 s");
    expect(runDuration(makeRun({ finishedAt: null }))).toBeNull();
  });

  it("flags last runs that need attention and splits recipients", () => {
    expect(needsAttention(makeSchedule())).toBe(true);
    expect(needsAttention(makeSchedule({ lastRun: null }))).toBe(false);
    const fine = makeRun({ riskLevel: "LOW", riskScore: 10, rtoFeasible: true });
    expect(needsAttention(makeSchedule({ lastRun: fine }))).toBe(false);
    expect(recipientsOf(" a@x.com, ,b@x.com ")).toEqual(["a@x.com", "b@x.com"]);
    expect(recipientsOf(" ")).toBeUndefined();
  });
});
