import { vi } from "vitest";
import type { AnalysisDetail, AnalysisSummary, ServiceHistory } from "../api/types";
import { makeExecution } from "./executionFixtures";
import { makeReport } from "./fixtures";

export function makeSummary(overrides: Partial<AnalysisSummary> = {}): AnalysisSummary {
  return {
    id: "job-1",
    serviceName: "Payment Gateway",
    owner: "Bob",
    source: "api",
    createdAt: "2026-09-25T08:59:30Z",
    completedAt: "2026-09-25T09:00:00Z",
    runbookLabel: "payment-gateway.md",
    inventoryLabel: "partial-outage.json",
    riskScore: 72,
    riskLevel: "HIGH",
    rtoFeasible: false,
    aiAnalysisAvailable: true,
    executionCount: 1,
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<AnalysisDetail> = {}): AnalysisDetail {
  return {
    summary: makeSummary(),
    report: makeReport(),
    provenance: {
      llmProvider: "openai_compatible",
      llmModel: "mistral-small-latest",
      promptVersion: "analysis/1",
      agentVersion: "0.1.0",
    },
    stale: false,
    ...overrides,
  };
}

/** Stubs for the history part of `Api`; override per test. */
export function historyApiStubs() {
  return {
    listAnalyses: vi.fn(async () => ({ items: [makeSummary()], nextBefore: null })),
    getAnalysis: vi.fn(async () => makeDetail()),
    analysisExecutions: vi.fn(async () => [
      {
        id: "exec-1",
        analysisJobId: "job-1",
        state: "COMPLETED" as const,
        mode: "live" as const,
        runbookLabel: "payment-gateway.md",
        startedBy: "Olivia",
        createdAt: "2026-09-25T09:10:00Z",
        updatedAt: "2026-09-25T09:40:00Z",
        steps: 3,
      },
    ]),
    analysisExecution: vi.fn(async () => ({
      execution: makeExecution({ state: "COMPLETED", mode: "live" }),
      audit: {
        events: [
          {
            seq: 1,
            executionId: "exec-1",
            type: "execution_created",
            actor: "Olivia",
            payload: {},
            prevHash: "0".repeat(64),
            hash: "1".repeat(64),
            createdAt: "2026-09-25T09:10:00Z",
          },
        ],
        verification: { valid: true, head: "1".repeat(64), events: 1, brokenAtSeq: null },
      },
    })),
    analysisRunbookUrl: (id: string) => `http://api.test/api/v1/analyses/${id}/runbook`,
    analysisReportHtmlUrl: (id: string) => `http://api.test/api/v1/analyses/${id}/report.html`,
  };
}

/** Two live runs: step 2 failed once and was rolled back once; one run went over the RTO. */
export function makeHistory(overrides: Partial<ServiceHistory> = {}): ServiceHistory {
  return {
    serviceName: "Payment Gateway",
    analysesConsidered: 3,
    liveRuns: 2,
    dryRuns: 1,
    riskScores: [60, 72],
    executions: [
      {
        executionId: "run-2",
        state: "COMPLETED",
        startedAt: "2026-09-24T10:00:00Z",
        elapsedMinutes: 42,
        statedRtoMinutes: 30,
      },
    ],
    steps: [
      {
        stepNumber: 2,
        fingerprint: "f".repeat(64),
        targetSystem: "payments-db",
        estimatedMinutes: 10,
        liveRuns: 2,
        succeeded: 0,
        failed: 1,
        rolledBack: 1,
        skipped: 0,
        manualDone: 0,
        unknown: 0,
        retries: 1,
        medianActiveMinutes: 18,
        maxActiveMinutes: 20,
        medianElapsedMinutes: 25,
      },
    ],
    dependencies: [
      { name: "payments-db", analyses: 3, up: 1, down: 2, unreachable: 0, notInInventory: 0 },
      { name: "internal-dns", analyses: 3, up: 3, down: 0, unreachable: 0, notInInventory: 0 },
    ],
    ...overrides,
  };
}
