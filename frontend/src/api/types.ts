// Aliases over the generated OpenAPI types (src/api/schema.d.ts). Never hand-write response shapes.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Report = Schemas["DRReadinessReport"];
export type JobView = Schemas["JobView"];
export type JobState = Schemas["JobState"];
export type ErrorBody = Schemas["ErrorBody"];
export type AnalyzeRequest = Schemas["AnalyzeJsonRequest"];
export type SystemInventory = Schemas["SystemInventory"];
export type SampleList = Schemas["SampleList"];
export type HealthResponse = Schemas["HealthResponse"];
export type RiskLevel = Schemas["RiskLevel"];
export type Severity = Schemas["Severity"];
export type GapType = Schemas["GapType"];
export type Gap = Schemas["Gap"];
export type DependencyHealth = Schemas["DependencyHealth"];
export type DependencyStatus = Schemas["DependencyStatus"];
export type ExecutionPhase = Schemas["ExecutionPhase"];
export type SinglePointOfFailure = Schemas["SinglePointOfFailure"];
export type Suggestion = Schemas["Suggestion"];
export type RtoAnalysis = Schemas["RtoAnalysis"];

// Execution (Phase 11)
export type Execution = Schemas["Execution"];
export type ExecutionSummary = Schemas["ExecutionSummary"];
export type ExecutionSettings = Schemas["ExecutionSettingsView"];
export type ExecutionState = Schemas["ExecutionState"];
export type ExecutionMode = Schemas["ExecutionMode"];
export type StepRun = Schemas["StepRun"];
export type StepState = Schemas["StepState"];
export type ToolCall = Schemas["ToolCall"];
export type PlannedToolCall = Schemas["PlannedToolCall"];
export type RiskClass = Schemas["RiskClass"];
export type CallSource = Schemas["CallSource"];
export type ToolView = Schemas["ToolView"];
export type AuditView = Schemas["AuditView"];
export type AuditEvent = Schemas["AuditEvent"];
export type CreateExecutionRequest = Schemas["CreateExecutionRequest"];
export type LifecycleRequest = Schemas["LifecycleRequest"];
export type ApproveRequest = Schemas["ApproveRequest"];
export type CallRequest = Schemas["CallRequest"];
export type StepDecisionRequest = Schemas["StepDecisionRequest"];
export type LifecycleAction = "start" | "pause" | "resume" | "abort" | "close";
export type StepAction =
  "reject" | "skip" | "manual" | "mark-done" | "verify" | "retry" | "rollback";

// Analysis history (Phase 13)
export type AnalysisSummary = Schemas["AnalysisSummary"];
export type AnalysisPage = Schemas["AnalysisPage"];
export type AnalysisDetail = Schemas["AnalysisDetail"];
export type StoredExecution = Schemas["StoredExecution"];

// Knowledge base (Phase 14)
export type ServiceHistory = Schemas["ServiceHistory"];
export type StepHistory = Schemas["StepHistory"];
