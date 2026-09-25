import { describe, expect, it, vi } from "vitest";
import { makeExecution } from "../test/executionFixtures";
import { ApiError, createApi } from "./client";

function recorder(body: unknown, status = 200) {
  const requests: { method: string; url: string; body: unknown }[] = [];
  const fetchImpl = vi.fn(async (input: Request) => {
    const text = await input.text();
    requests.push({ method: input.method, url: input.url, body: text ? JSON.parse(text) : null });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  return { api: createApi("http://api.test", fetchImpl as unknown as typeof fetch), requests };
}

describe("execution client", () => {
  it("sends every execution request to the documented path", async () => {
    const execution = makeExecution();
    const { api, requests } = recorder(execution);
    await api.createExecution({ analysisJobId: "job-1", mode: "dry_run", startedBy: "Olivia" });
    await api.getExecution("exec-1");
    await api.changeExecution("exec-1", "abort", { actor: "Olivia", reason: "drill over" });
    await api.approveStep("exec-1", 2, { approver: "Ann", callHash: "b".repeat(64), kind: "main" });
    await api.decideStep("exec-1", 2, "skip", { actor: "Ann", reason: "done", succeeded: null });
    await api.setCall("exec-1", 2, { editor: "Ann", kind: "main", call: null });
    expect(requests.map((r) => `${r.method} ${r.url}`)).toEqual([
      "POST http://api.test/api/v1/executions",
      "GET http://api.test/api/v1/executions/exec-1",
      "POST http://api.test/api/v1/executions/exec-1/abort",
      "POST http://api.test/api/v1/executions/exec-1/steps/2/approve",
      "POST http://api.test/api/v1/executions/exec-1/steps/2/skip",
      "PUT http://api.test/api/v1/executions/exec-1/steps/2/call",
    ]);
    expect(requests.at(3)?.body).toMatchObject({ approver: "Ann", kind: "main" });
  });

  it("reads settings, tools, the list and the verified audit log", async () => {
    const { api, requests } = recorder([]);
    await api.executionSettings();
    await api.listTools();
    await api.listExecutions();
    await api.getAudit("exec-1");
    expect(requests.map((r) => r.url)).toEqual([
      "http://api.test/api/v1/execution/settings",
      "http://api.test/api/v1/tools",
      "http://api.test/api/v1/executions",
      "http://api.test/api/v1/executions/exec-1/audit?verify=true",
    ]);
  });

  it("turns the server's refusal into an ApiError", async () => {
    const { api } = recorder({ error: "the call changed", code: "STALE_CALL" }, 409);
    const refused = api.approveStep("exec-1", 1, {
      approver: "Ann",
      callHash: "0".repeat(64),
      kind: "main",
    });
    await expect(refused).rejects.toEqual(new ApiError("the call changed", "STALE_CALL", 409));
  });
});
