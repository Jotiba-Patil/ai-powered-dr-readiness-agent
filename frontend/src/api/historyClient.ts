// Analysis history endpoints (design analysis-history section 6).
import type { Client } from "openapi-fetch";
import { call } from "./http";
import type { paths } from "./schema";
import type {
  AnalysisDetail,
  AnalysisPage,
  ExecutionSummary,
  RiskLevel,
  StoredExecution,
} from "./types";

export interface AnalysisQuery {
  service?: string;
  riskLevel?: RiskLevel;
  limit?: number;
  /** `nextBefore` of the previous page. */
  before?: string;
}

export function createHistoryApi(root: string, client: Client<paths>) {
  const path = (analysisId: string) => `${root}/api/v1/analyses/${encodeURIComponent(analysisId)}`;

  return {
    listAnalyses(query: AnalysisQuery = {}): Promise<AnalysisPage> {
      return call(root, () => client.GET("/api/v1/analyses", { params: { query } }));
    },

    getAnalysis(analysisId: string): Promise<AnalysisDetail> {
      return call(root, () =>
        client.GET("/api/v1/analyses/{analysis_id}", {
          params: { path: { analysis_id: analysisId } },
        }),
      );
    },

    /** Executions created from this analysis (readable even while execution is off). */
    analysisExecutions(analysisId: string): Promise<ExecutionSummary[]> {
      return call(root, () =>
        client.GET("/api/v1/analyses/{analysis_id}/executions", {
          params: { path: { analysis_id: analysisId } },
        }),
      );
    },

    /** One past execution with its steps and verified audit log (read-only). */
    analysisExecution(analysisId: string, executionId: string): Promise<StoredExecution> {
      return call(root, () =>
        client.GET("/api/v1/analyses/{analysis_id}/executions/{execution_id}", {
          params: { path: { analysis_id: analysisId, execution_id: executionId } },
        }),
      );
    },

    /** The stored runbook Markdown, served as a plain-text download. */
    analysisRunbookUrl(analysisId: string): string {
      return `${path(analysisId)}/runbook`;
    },

    analysisReportHtmlUrl(analysisId: string): string {
      return `${path(analysisId)}/report.html`;
    },
  };
}
