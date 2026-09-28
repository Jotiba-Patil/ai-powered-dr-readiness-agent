import { vi } from "vitest";
import type { ScheduleRun, SchedulerView, ScheduleView } from "../api/types";

export function makeRun(overrides: Partial<ScheduleRun> = {}): ScheduleRun {
  return {
    id: "run-1",
    scheduleId: "sched-1",
    slotAt: "2026-09-27T06:00:00Z",
    trigger: "scheduled",
    state: "succeeded",
    startedAt: "2026-09-27T06:00:00Z",
    finishedAt: "2026-09-27T06:02:00Z",
    jobId: "job-1",
    analysisId: "job-1",
    riskScore: 72,
    riskLevel: "HIGH",
    rtoFeasible: false,
    emailState: "sent",
    emailTo: ["alice.chen@example.com"],
    errorCode: null,
    error: null,
    ...overrides,
  };
}

export function makeSchedule(overrides: Partial<ScheduleView> = {}): ScheduleView {
  return {
    id: "sched-1",
    name: "Payment daily",
    runbookPath: "runbooks/payment-gateway.md",
    inventoryPath: "inventories/healthy.json",
    cadence: { kind: "daily", time: "06:00" },
    timezone: "UTC",
    recipients: null,
    enabled: true,
    pauseUntil: null,
    pausedBy: null,
    pausedAt: null,
    createdBy: "Alice",
    createdAt: "2026-09-26T10:00:00Z",
    updatedAt: "2026-09-26T10:00:00Z",
    nextRunAt: "2026-09-28T06:00:00Z",
    lastRunAt: "2026-09-27T06:00:00Z",
    description: "Daily 06:00 UTC",
    lastRun: makeRun(),
    ...overrides,
  };
}

export function makeScheduler(overrides: Partial<SchedulerView> = {}): SchedulerView {
  return {
    paused: false,
    pauseUntil: null,
    pausedBy: null,
    pausedAt: null,
    tickSeconds: 30,
    maxSchedules: 50,
    maxPauseDays: 90,
    defaultTimezone: "UTC",
    emailTransport: "smtp",
    defaultRecipient: true,
    allowedDomains: ["example.com"],
    ...overrides,
  };
}

/** Stubs for the schedule part of `Api`; override per test. */
export function scheduleApiStubs() {
  return {
    listSchedules: vi.fn(async () => [makeSchedule()]),
    createSchedule: vi.fn(async () => makeSchedule({ id: "sched-2", lastRun: null })),
    updateSchedule: vi.fn(async () => makeSchedule()),
    deleteSchedule: vi.fn(async () => undefined),
    pauseSchedule: vi.fn(async (_id: string, by: string, until?: string) =>
      makeSchedule({ enabled: false, pausedBy: by, pauseUntil: until ?? null, nextRunAt: null }),
    ),
    resumeSchedule: vi.fn(async () => makeSchedule()),
    runScheduleNow: vi.fn(async () =>
      makeRun({ id: "run-2", state: "running", trigger: "manual" }),
    ),
    listScheduleRuns: vi.fn(async () => ({ items: [makeRun()], nextBefore: null })),
    getScheduleRun: vi.fn(async () => makeRun()),
    cancelScheduleRun: vi.fn(async () => makeRun({ state: "cancelled" })),
    schedulerState: vi.fn(async () => makeScheduler()),
    pauseAll: vi.fn(async (by: string) => makeScheduler({ paused: true, pausedBy: by })),
    resumeAll: vi.fn(async () => makeScheduler()),
    previewRecipients: vi.fn(async () => ({
      addresses: ["alice.chen@example.com"],
      source: "directory" as const,
      ownerFound: true,
      dropped: 0,
    })),
  };
}
