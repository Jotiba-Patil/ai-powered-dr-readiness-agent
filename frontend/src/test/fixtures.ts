import { vi } from "vitest";
import type { Api } from "../api/client";
import type { JobView, Report } from "../api/types";
import { executionApiStubs } from "./executionFixtures";
import { historyApiStubs } from "./historyFixtures";

export function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    meta: {
      analyzedAt: "2026-09-22T12:00:00Z",
      runbookFile: "payment-gateway.md",
      inventoryFile: "partial-outage.json",
      agentVersion: "0.1.0",
      analysisTimeMs: 1500,
    },
    serviceSummary: { name: "Payment Gateway", owner: "Bob", statedRTO: 30, statedRPO: 5 },
    riskScore: 72,
    riskLevel: "HIGH",
    rtoAnalysis: {
      feasible: false,
      totalEstimatedMinutes: 45,
      statedRtoMinutes: 30,
      bufferMinutes: -15,
      bottleneckSteps: [3],
    },
    dependencyHealth: [
      { name: "payments-db", runbookAssumes: "available", actualStatus: "DOWN", impact: "step 2" },
      {
        name: "card-network-gateway",
        runbookAssumes: "available",
        actualStatus: "NOT_IN_INVENTORY",
        impact: "step 4",
      },
      { name: "internal-dns", runbookAssumes: "available", actualStatus: "UP", impact: "none" },
    ],
    singlePointsOfFailure: [
      {
        description: "Only Bob can fail over",
        affectedSteps: [2, 3],
        mitigationSuggestion: "Train a backup",
      },
    ],
    gapAnalysis: [
      {
        type: "OWNER_AMBIGUITY",
        description: "Step 2 owned by team",
        severity: "HIGH",
        recommendation: "Name a person",
      },
      {
        type: "NO_VALIDATION",
        description: "Step 4 has no check",
        severity: "MEDIUM",
        recommendation: "Add a check",
      },
      {
        type: "VAGUE_INSTRUCTION",
        description: "Step 1 is vague",
        severity: "LOW",
        recommendation: "Be specific",
      },
    ],
    executionPlan: [
      { phase: 1, steps: [1, 2], estimatedMinutes: 20, gate: "none: initial phase" },
      { phase: 2, steps: [3], estimatedMinutes: 25, gate: "step(s) 2 complete" },
    ],
    suggestions: [
      { priority: 2, title: "Automate DNS", detail: "Script the cutover" },
      { priority: 1, title: "Rehearse failover", detail: "Quarterly drill" },
    ],
    summary: "The runbook cannot meet its RTO.",
    aiAnalysisAvailable: true,
    aiNote: null,
    ...overrides,
  };
}

export function makeJob(overrides: Partial<JobView> = {}): JobView {
  return { jobId: "job-1", status: "pending", createdAt: "2026-09-22T12:00:00Z", ...overrides };
}

/** A stub `Api` whose methods are vi.fn()s; override per test. */
export function makeApi(overrides: Partial<Api> = {}): Api {
  return {
    baseUrl: "http://api.test",
    health: vi.fn(async () => ({ status: "ok" as const, version: "0.1.0", uptime: 12 })),
    submitAnalysis: vi.fn(async () => makeJob()),
    pollJob: vi.fn(async () => makeJob({ status: "succeeded", report: makeReport() })),
    listSamples: vi.fn(async () => ({
      runbooks: ["runbooks/auth-service.md", "runbooks/payment-gateway.md"],
      inventories: ["inventories/healthy.json"],
    })),
    getSample: vi.fn(async (path: string) =>
      path.endsWith(".json") ? '{"services": []}' : "# Auth Service\n",
    ),
    reportHtmlUrl: (jobId: string) => `http://api.test/api/v1/dr/jobs/${jobId}/report.html`,
    ...executionApiStubs(),
    ...historyApiStubs(),
    ...overrides,
  };
}
