import { describe, expect, it, vi } from "vitest";
import { ApiError, createApi } from "./client";

function recorder(body: unknown, status = 200) {
  const urls: string[] = [];
  const fetchImpl = vi.fn(async (input: Request) => {
    urls.push(`${input.method} ${input.url}`);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  return { api: createApi("http://api.test", fetchImpl as unknown as typeof fetch), urls };
}

describe("history client", () => {
  it("lists with filters and reads one analysis", async () => {
    const { api, urls } = recorder({ items: [], nextBefore: null });
    await api.listAnalyses();
    await api.listAnalyses({ service: "Payment Gateway", riskLevel: "HIGH", limit: 5 });
    await api.getAnalysis("job-1");
    expect(urls).toEqual([
      "GET http://api.test/api/v1/analyses",
      "GET http://api.test/api/v1/analyses?service=Payment%20Gateway&riskLevel=HIGH&limit=5",
      "GET http://api.test/api/v1/analyses/job-1",
    ]);
  });

  it("builds download links and escapes the id", () => {
    const { api } = recorder({});
    expect(api.analysisRunbookUrl("a/b")).toBe("http://api.test/api/v1/analyses/a%2Fb/runbook");
    expect(api.analysisReportHtmlUrl("job-1")).toBe(
      "http://api.test/api/v1/analyses/job-1/report.html",
    );
  });

  it("turns a disabled history into an ApiError with its code", async () => {
    const { api } = recorder({ error: "off", code: "HISTORY_DISABLED" }, 403);
    await expect(api.listAnalyses()).rejects.toEqual(new ApiError("off", "HISTORY_DISABLED", 403));
  });
});
