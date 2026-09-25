import { describe, expect, it, vi } from "vitest";
import { ApiError, createApi } from "./client";

type Handler = (request: Request) => Response | Promise<Response>;

function apiWith(handler: Handler, baseUrl = "http://api.test/") {
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => handler(input as Request));
  return { api: createApi(baseUrl, fetchImpl as unknown as typeof fetch), fetchImpl };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const job = { jobId: "abc", status: "pending", createdAt: "2026-09-22T12:00:00Z" };

describe("createApi", () => {
  it("strips trailing slashes from the base URL", () => {
    expect(apiWith(() => json({})).api.baseUrl).toBe("http://api.test");
  });

  it("submits a JSON analysis and returns the job", async () => {
    let seen: Request | undefined;
    const { api } = apiWith(async (request) => {
      seen = request;
      return json(job, 202);
    });
    await expect(
      api.submitAnalysis({ runbookMarkdown: "# X", inventory: null, runbookName: null }),
    ).resolves.toEqual(job);
    expect(seen?.method).toBe("POST");
    expect(seen?.url).toBe("http://api.test/api/v1/dr/analyze");
    await expect(seen?.json()).resolves.toEqual({
      runbookMarkdown: "# X",
      inventory: null,
      runbookName: null,
    });
  });

  it("rejects a submit response that is not a job", async () => {
    const { api } = apiWith(() => json({ riskScore: 1 }));
    await expect(
      api.submitAnalysis({ runbookMarkdown: "# X", inventory: null, runbookName: null }),
    ).rejects.toMatchObject({
      code: "BAD_RESPONSE",
    });
  });

  it("maps the API error shape to ApiError", async () => {
    const { api } = apiWith(() => json({ error: "bad runbook", code: "PARSE_ERROR" }, 422));
    const error = await api
      .submitAnalysis({ runbookMarkdown: "x", inventory: null, runbookName: null })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: "bad runbook", code: "PARSE_ERROR", status: 422 });
  });

  it("falls back to a generic error for unknown error bodies", async () => {
    const { api } = apiWith(() => json({ detail: "nope" }, 500));
    await expect(api.listSamples()).rejects.toMatchObject({ code: "HTTP_ERROR", status: 500 });
  });

  it("reports an unreachable API as NETWORK_ERROR", async () => {
    const { api } = apiWith(() => {
      throw new TypeError("Failed to fetch");
    });
    await expect(api.listSamples()).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
  });

  it("uses relative URLs when the base URL is empty (same origin)", async () => {
    const { api } = apiWith(() => {
      throw new TypeError("offline");
    }, "");
    expect(api.baseUrl).toBe("");
    expect(api.reportHtmlUrl("a b")).toBe("/api/v1/dr/jobs/a%20b/report.html");
    await expect(api.listSamples()).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      message: "Cannot reach the API. Is it running?",
    });
  });

  it("long-polls a job with wait=true", async () => {
    let url = "";
    const { api } = apiWith((request) => {
      url = request.url;
      return json({ ...job, status: "running" });
    });
    await expect(api.pollJob("abc")).resolves.toMatchObject({ status: "running" });
    expect(url).toBe("http://api.test/api/v1/dr/jobs/abc?wait=true");
  });

  it("lists samples and reads one", async () => {
    const { api } = apiWith((request) =>
      request.url.includes("/file")
        ? json({ path: "runbooks/a.md", content: "# A" })
        : json({ runbooks: ["runbooks/a.md"], inventories: [] }),
    );
    await expect(api.listSamples()).resolves.toEqual({
      runbooks: ["runbooks/a.md"],
      inventories: [],
    });
    await expect(api.getSample("runbooks/a.md")).resolves.toBe("# A");
  });

  it("builds an encoded HTML export URL", () => {
    expect(apiWith(() => json({})).api.reportHtmlUrl("a b")).toBe(
      "http://api.test/api/v1/dr/jobs/a%20b/report.html",
    );
  });
});
