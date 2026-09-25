// The one typed API client. Every call goes through openapi-fetch with the generated `paths`.
import createClient from "openapi-fetch";
import { createExecutionApi } from "./executionClient";
import { createHistoryApi } from "./historyClient";
import { ApiError, call } from "./http";
import type { paths } from "./schema";
import type { AnalyzeRequest, HealthResponse, JobView, SampleList } from "./types";

export { ApiError } from "./http";

export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

/** An empty base URL means same origin (the Docker UI proxies `/api` to the API). */
export function createApi(baseUrl: string = DEFAULT_API_BASE_URL, fetchImpl?: typeof fetch) {
  const root = baseUrl.replace(/\/+$/, "");
  const client = createClient<paths>({ baseUrl: root, fetch: fetchImpl });

  return {
    baseUrl: root,
    ...createExecutionApi(root, client),
    ...createHistoryApi(root, client),

    /** Starts an analysis job (never waits: a local model on CPU takes minutes). */
    async submitAnalysis(body: AnalyzeRequest): Promise<JobView> {
      const data = await call(root, () => client.POST("/api/v1/dr/analyze", { body }));
      if (!("jobId" in data)) {
        throw new ApiError("Unexpected response: no job id", "BAD_RESPONSE", 200);
      }
      return data;
    },

    /** Long-polls a job: the server holds the request until done or its wait timeout. */
    pollJob(jobId: string): Promise<JobView> {
      return call(root, () =>
        client.GET("/api/v1/dr/jobs/{job_id}", {
          params: { path: { job_id: jobId }, query: { wait: true } },
        }),
      );
    },

    health(): Promise<HealthResponse> {
      return call(root, () => client.GET("/api/v1/health"));
    },

    listSamples(): Promise<SampleList> {
      return call(root, () => client.GET("/api/v1/dr/samples"));
    },

    async getSample(path: string): Promise<string> {
      const data = await call(root, () =>
        client.GET("/api/v1/dr/samples/file", { params: { query: { path } } }),
      );
      return data.content;
    },

    reportHtmlUrl(jobId: string): string {
      return `${root}/api/v1/dr/jobs/${encodeURIComponent(jobId)}/report.html`;
    },
  };
}

export type Api = ReturnType<typeof createApi>;

export const api = createApi(import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL);
