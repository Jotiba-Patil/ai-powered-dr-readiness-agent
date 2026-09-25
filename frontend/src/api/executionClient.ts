// Execution endpoints (design section 8). All checks are server-side; this only sends requests.
import type { Client } from "openapi-fetch";
import { call } from "./http";
import type { paths } from "./schema";
import type {
  ApproveRequest,
  AuditView,
  CallRequest,
  CreateExecutionRequest,
  Execution,
  ExecutionSettings,
  ExecutionSummary,
  LifecycleAction,
  LifecycleRequest,
  StepAction,
  StepDecisionRequest,
  ToolView,
} from "./types";

export function createExecutionApi(root: string, client: Client<paths>) {
  const ids = (executionId: string, stepNumber: number) => ({
    path: { execution_id: executionId, step_number: stepNumber },
  });

  return {
    executionSettings(): Promise<ExecutionSettings> {
      return call(root, () => client.GET("/api/v1/execution/settings"));
    },

    listTools(): Promise<ToolView[]> {
      return call(root, () => client.GET("/api/v1/tools"));
    },

    listExecutions(): Promise<ExecutionSummary[]> {
      return call(root, () => client.GET("/api/v1/executions"));
    },

    getExecution(executionId: string): Promise<Execution> {
      return call(root, () =>
        client.GET("/api/v1/executions/{execution_id}", {
          params: { path: { execution_id: executionId } },
        }),
      );
    },

    createExecution(body: CreateExecutionRequest): Promise<Execution> {
      return call(root, () => client.POST("/api/v1/executions", { body }));
    },

    changeExecution(
      executionId: string,
      action: LifecycleAction,
      body: LifecycleRequest,
    ): Promise<Execution> {
      return call(root, () =>
        client.POST("/api/v1/executions/{execution_id}/{action}", {
          params: { path: { execution_id: executionId, action } },
          body,
        }),
      );
    },

    setCall(executionId: string, stepNumber: number, body: CallRequest): Promise<Execution> {
      return call(root, () =>
        client.PUT("/api/v1/executions/{execution_id}/steps/{step_number}/call", {
          params: ids(executionId, stepNumber),
          body,
        }),
      );
    },

    approveStep(executionId: string, stepNumber: number, body: ApproveRequest): Promise<Execution> {
      return call(root, () =>
        client.POST("/api/v1/executions/{execution_id}/steps/{step_number}/approve", {
          params: ids(executionId, stepNumber),
          body,
        }),
      );
    },

    decideStep(
      executionId: string,
      stepNumber: number,
      action: StepAction,
      body: StepDecisionRequest,
    ): Promise<Execution> {
      return call(root, () =>
        client.POST("/api/v1/executions/{execution_id}/steps/{step_number}/{action}", {
          params: { path: { execution_id: executionId, step_number: stepNumber, action } },
          body,
        }),
      );
    },

    getAudit(executionId: string): Promise<AuditView> {
      return call(root, () =>
        client.GET("/api/v1/executions/{execution_id}/audit", {
          params: { path: { execution_id: executionId }, query: { verify: true } },
        }),
      );
    },
  };
}

export type ExecutionApi = ReturnType<typeof createExecutionApi>;
