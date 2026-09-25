import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { AnalyzeRequest, JobView } from "../api/types";
import { makeApi, makeJob, makeReport } from "../test/fixtures";
import { useAnalysis } from "./useAnalysis";
import { useSamples } from "./useSamples";

const request: AnalyzeRequest = { runbookMarkdown: "# X", inventory: null, runbookName: null };

describe("useAnalysis", () => {
  it("polls until the job succeeds", async () => {
    const pollJob = vi
      .fn()
      .mockResolvedValueOnce(makeJob({ status: "running" }))
      .mockResolvedValueOnce(makeJob({ status: "succeeded", report: makeReport() }));
    const api = makeApi({ pollJob });
    const { result } = renderHook(() => useAnalysis(api, 0));

    await act(() => result.current.analyze(request));

    expect(pollJob).toHaveBeenCalledTimes(2);
    expect(result.current.state).toMatchObject({ phase: "done", jobId: "job-1" });
  });

  it("reports a failed job's error", async () => {
    const failed = makeJob({ status: "failed", error: { error: "boom", code: "INTERNAL_ERROR" } });
    const api = makeApi({ pollJob: vi.fn(async () => failed) });
    const { result } = renderHook(() => useAnalysis(api, 0));

    await act(() => result.current.analyze(request));

    expect(result.current.state).toMatchObject({
      phase: "error",
      error: { code: "INTERNAL_ERROR" },
    });
  });

  it("uses a generic error when a failed job carries none", async () => {
    const api = makeApi({ pollJob: vi.fn(async () => makeJob({ status: "failed" })) });
    const { result } = renderHook(() => useAnalysis(api, 0));
    await act(() => result.current.analyze(request));
    expect(result.current.state).toMatchObject({ error: { code: "ANALYSIS_FAILED" } });
  });

  it("surfaces API errors from submit", async () => {
    const error = new ApiError("bad", "PARSE_ERROR", 422);
    const api = makeApi({ submitAnalysis: vi.fn().mockRejectedValue(error) });
    const { result } = renderHook(() => useAnalysis(api, 0));
    await act(() => result.current.analyze(request));
    expect(result.current.state).toEqual({ phase: "error", error });
  });

  it("wraps unexpected errors", async () => {
    const api = makeApi({ submitAnalysis: vi.fn().mockRejectedValue(new Error("x")) });
    const { result } = renderHook(() => useAnalysis(api, 0));
    await act(() => result.current.analyze(request));
    expect(result.current.state).toMatchObject({ error: { code: "CLIENT_ERROR" } });
  });

  it("ignores a run's result after reset", async () => {
    let finish: (value: JobView) => void = () => {};
    const api = makeApi({ pollJob: vi.fn(() => new Promise<JobView>((r) => (finish = r))) });
    const { result } = renderHook(() => useAnalysis(api, 0));

    let running: Promise<void> = Promise.resolve();
    act(() => {
      running = result.current.analyze(request);
    });
    await waitFor(() => expect(result.current.state.phase).toBe("running"));
    act(() => result.current.reset());
    await act(async () => {
      finish(makeJob({ status: "succeeded", report: makeReport() }));
      await running;
    });

    expect(result.current.state).toEqual({ phase: "idle" });
  });
});

describe("useSamples", () => {
  it("loads the sample list and file contents", async () => {
    const api = makeApi();
    const { result } = renderHook(() => useSamples(api));
    await waitFor(() => expect(result.current.samples.runbooks).toHaveLength(2));
    await expect(result.current.load("runbooks/auth-service.md")).resolves.toContain("# Auth");
    expect(result.current.error).toBeNull();
  });

  it("exposes a listing error", async () => {
    const api = makeApi({ listSamples: vi.fn().mockRejectedValue(new Error("offline")) });
    const { result } = renderHook(() => useSamples(api));
    await waitFor(() => expect(result.current.error).toBe("offline"));
  });
});
