import { vi } from "vitest";
import type { Execution, StepRun, ToolCall } from "../api/types";

const HASH = (c: string) => c.repeat(64);

export function makeCall(overrides: Partial<ToolCall> = {}): ToolCall {
  return {
    kind: "main",
    server: "drsim",
    tool: "cache_ping",
    arguments: { cache: "pricing-cache" },
    source: "annotated",
    riskClass: "read",
    callHash: HASH("a"),
    approvals: [],
    ...overrides,
  };
}

export function makeStep(overrides: Partial<StepRun> = {}): StepRun {
  return {
    stepNumber: 1,
    phase: 1,
    action: "Ping the cache",
    owner: "Bob",
    estimatedMinutes: 5,
    state: "AWAITING_APPROVAL",
    attempt: 1,
    call: makeCall(),
    policyErrors: [],
    dependsOn: [],
    ...overrides,
  };
}

/** Three steps: a read call, a destructive call with a rollback, and a manual step. */
export function makeExecution(overrides: Partial<Execution> = {}): Execution {
  return {
    id: "exec-1",
    state: "CREATED",
    mode: "dry_run",
    runbookLabel: "estimate-service-executable.md",
    runbookSha256: HASH("0"),
    startedBy: "Olivia",
    createdAt: "2026-09-24T09:00:00Z",
    updatedAt: "2026-09-24T09:00:00Z",
    toolCallsUsed: 0,
    auditSeq: 6,
    auditHead: HASH("f"),
    steps: [
      makeStep(),
      makeStep({
        stepNumber: 2,
        phase: 2,
        action: "Promote the replica",
        dependsOn: [1],
        call: makeCall({
          tool: "db_promote_replica",
          arguments: { cluster: "estimate-postgres" },
          riskClass: "destructive",
          callHash: HASH("b"),
        }),
        rollback: makeCall({
          kind: "rollback",
          tool: "dns_switch_region",
          riskClass: "destructive",
          callHash: HASH("c"),
        }),
      }),
      makeStep({
        stepNumber: 3,
        phase: 2,
        action: "Call the vendor",
        state: "AWAITING_MANUAL",
        call: null,
        summary: "no tool annotation: manual step",
      }),
    ],
    ...overrides,
  };
}

/** Execution endpoints for `makeApi`; every mutation answers with the same execution. */
export function executionApiStubs(execution: Execution = makeExecution()) {
  const answer = vi.fn(async () => execution);
  return {
    executionSettings: vi.fn(async () => ({
      enabled: true,
      allowLive: true,
      approvalTimeoutMinutes: 30,
      maxToolCalls: 50,
      approvalsByRisk: { read: 1, write: 1, destructive: 2 },
      identityVerified: false as const,
    })),
    listTools: vi.fn(async () => []),
    listExecutions: vi.fn(async () => [
      {
        id: execution.id,
        analysisJobId: "job-1",
        state: execution.state,
        mode: execution.mode,
        runbookLabel: execution.runbookLabel,
        startedBy: execution.startedBy,
        createdAt: execution.createdAt,
        updatedAt: execution.updatedAt,
        steps: execution.steps.length,
      },
    ]),
    getExecution: answer,
    createExecution: vi.fn(async () => execution),
    changeExecution: vi.fn(async () => execution),
    setCall: vi.fn(async () => execution),
    approveStep: vi.fn(async () => execution),
    decideStep: vi.fn(async () => execution),
    getAudit: vi.fn(async () => ({
      events: [
        {
          seq: 1,
          executionId: execution.id,
          type: "execution_created",
          actor: "Olivia",
          payload: { mode: "dry_run" },
          prevHash: HASH("0"),
          hash: HASH("1"),
          createdAt: "2026-09-24T09:00:00Z",
        },
      ],
      verification: { valid: true, head: HASH("1"), events: 1, brokenAtSeq: null },
    })),
  };
}
