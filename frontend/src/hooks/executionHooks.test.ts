import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { makeExecution } from "../test/executionFixtures";
import { makeApi } from "../test/fixtures";
import { useAudit } from "./useAudit";
import { useExecution } from "./useExecution";
import { useExecutionCatalog } from "./useExecutionCatalog";
import { useStoredName } from "./useStoredName";

describe("useExecution", () => {
  it("shows the answer of an action, or its error", async () => {
    const api = makeApi();
    const { result } = renderHook(() => useExecution(api, 0));
    await act(() => result.current.open("exec-1"));
    expect(result.current.execution?.id).toBe("exec-1");
    const refused = new ApiError("stale", "STALE_CALL", 409);
    await act(() => result.current.run(() => Promise.reject(refused)));
    expect(result.current.error).toBe(refused);
    act(() => result.current.dismissError());
    expect(result.current.error).toBeNull();
    await act(() => result.current.run(() => Promise.reject(new Error("x"))));
    expect(result.current.error?.code).toBe("CLIENT_ERROR");
    act(() => result.current.clear());
    expect(result.current.execution).toBeNull();
  });

  it("polls while the execution runs and stops when it no longer does", async () => {
    const running = makeExecution({ state: "RUNNING", updatedAt: "t1" });
    const getExecution = vi
      .fn()
      .mockResolvedValueOnce(makeExecution({ state: "RUNNING", updatedAt: "t2" }))
      .mockResolvedValueOnce(makeExecution({ state: "COMPLETED", updatedAt: "t3" }));
    const api = makeApi({ getExecution });
    const { result } = renderHook(() => useExecution(api, 0));
    await act(() => result.current.run(async () => running));
    await waitFor(() => expect(result.current.execution?.state).toBe("COMPLETED"));
    expect(getExecution).toHaveBeenCalledTimes(2);
  });

  it("reports a failed poll", async () => {
    const getExecution = vi.fn().mockRejectedValue(new ApiError("gone", "NOT_FOUND", 404));
    const api = makeApi({ getExecution });
    const { result } = renderHook(() => useExecution(api, 0));
    await act(() => result.current.run(async () => makeExecution({ state: "RUNNING" })));
    await waitFor(() => expect(result.current.error?.code).toBe("NOT_FOUND"));
  });
});

describe("useExecutionCatalog", () => {
  it("lists executions only when execution is enabled", async () => {
    const api = makeApi();
    const { result } = renderHook(() => useExecutionCatalog(api));
    await waitFor(() => expect(result.current.executions).toHaveLength(1));
    expect(result.current.settings?.enabled).toBe(true);

    const off = makeApi({
      executionSettings: vi.fn(async () => ({
        enabled: false,
        allowLive: false,
        approvalTimeoutMinutes: 30,
        maxToolCalls: 50,
        approvalsByRisk: {},
        identityVerified: false as const,
      })),
    });
    const disabled = renderHook(() => useExecutionCatalog(off));
    await waitFor(() => expect(disabled.result.current.settings?.enabled).toBe(false));
    expect(off.listExecutions).not.toHaveBeenCalled();
  });

  it("exposes loading errors", async () => {
    const api = makeApi({
      executionSettings: vi.fn().mockRejectedValue(new Error("offline")),
      listExecutions: vi.fn().mockRejectedValue(new Error("nope")),
    });
    const { result } = renderHook(() => useExecutionCatalog(api));
    await waitFor(() => expect(result.current.error).toBe("offline"));
    await act(() => result.current.refresh());
    expect(result.current.error).toBe("nope");
  });
});

describe("useAudit", () => {
  it("loads the verified log and reports errors", async () => {
    const api = makeApi();
    const { result } = renderHook(() => useAudit(api));
    await act(() => result.current.load("exec-1"));
    expect(result.current.audit?.verification?.valid).toBe(true);
    const failing = makeApi({ getAudit: vi.fn().mockRejectedValue(new Error("down")) });
    const other = renderHook(() => useAudit(failing));
    await act(() => other.result.current.load("exec-1"));
    expect(other.result.current.error).toBe("down");
  });
});

describe("useStoredName", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("remembers the name in this browser", () => {
    const first = renderHook(() => useStoredName());
    act(() => first.result.current[1]("Ann"));
    expect(renderHook(() => useStoredName()).result.current[0]).toBe("Ann");
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useStoredName());
    expect(result.current[0]).toBe("");
    act(() => result.current[1]("Ben"));
    expect(result.current[0]).toBe("Ben");
  });
});
