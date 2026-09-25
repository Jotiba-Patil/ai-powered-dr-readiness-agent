# PROJECT BRIEF: AI-Powered Disaster Recovery Readiness Agent (Production-Grade PoC) 

## 🎯 What You're Building 

An AI-powered CLI tool and REST API that reads Markdown-based Disaster Recovery (DR) 
Runbooks, extracts structured recovery steps, validates them against system health 
inventories, and uses an LLM (Claude API) to generate a comprehensive DR Readiness 
Report — including risk scoring, gap detection, RTO feasibility analysis, and 
actionable recommendations. 

This is a PoC but must be built to *production-grade standards* — clean architecture, 
proper error handling, logging, test coverage, typed throughout, and deployable. 

--- 

## 📖 Business Context (Read This Carefully) 

### The Problem 
Enterprise organizations maintain DR runbooks — step-by-step documents guiding teams 
through system restoration after outages. These runbooks suffer from critical issues: 

1. *Written manually, rarely validated* — teams discover gaps only during real incidents 
2. *Never cross-checked against live systems* — a runbook may reference services that 
 have been deprecated, moved, or are currently unhealthy 
3. *Dependent on human interpretation under pressure* — different responders read the 
 same steps differently at 2 AM during an outage 
4. *No continuous readiness posture* — DR is tested once or twice a year in scheduled 
 exercises, leaving months of drift undetected 
5. *RTO/RPO targets are aspirational* — nobody validates whether the documented steps 
 can actually be completed within the stated Recovery Time Objective 

### What This Tool Does 
- Parses any markdown DR runbook and extracts structured metadata (service, owner, 
 RTO, RPO, dependencies, ordered recovery steps with owners and time estimates) 
- Validates extracted dependencies against a system health inventory (mocked for PoC) 
- Uses AI (Claude) to perform intelligent analysis: 
 - Dependency chain reasoning (if Step 2 fails, what downstream steps are impacted?) 
 - RTO feasibility (can all steps complete within the stated target?) 
 - Single points of failure detection 
 - Risk scoring (0-100) 
 - Actionable improvement suggestions 
- Outputs a structured, human-readable readiness report (JSON + formatted terminal output) 

### Who Uses It 
- SREs and DevOps engineers (primary — via CLI) 
- Engineering managers (readiness reports for review) 
- Compliance teams (audit evidence) 

--- 

## 🏗️ Technical Stack (Non-Negotiable) 

| Layer | Technology | 
|--------------------|-----------------------------------------------------| 
| Runtime | Node.js 20+ (ESM modules throughout) | 
| Language | TypeScript 5+ (strict mode, no any) | 
| CLI Framework | commander | 
| Web Framework | fastify v4 | 
| LLM Integration | @anthropic-ai/sdk (Claude API with tool_use) | 
| Markdown Parsing | unified + remark-parse + mdast-util-to-string | 
| Schema Validation | zod v3 | 
| HTTP Client | Native fetch (Node 20+) | 
| Logging | pino | 
| Testing | vitest | 
| Build | tsup | 
| Dev Runner | tsx | 
| Linting | eslint + @typescript-eslint | 
| Formatting | prettier | 

--- 

## 📁 Target Project Structure 

 
dr-readiness-agent/ 
├── README.md 
├── package.json 
├── tsconfig.json 
├── tsup.config.ts 
├── vitest.config.ts 
├── .env.example # ANTHROPIC_API_KEY, PORT, LOG_LEVEL 
├── .eslintrc.cjs 
├── .prettierrc 
│ 
├── src/ 
│ ├── index.ts # CLI entry point 
│ ├── server.ts # Fastify REST API entry point 
│ ├── config.ts # Centralized config (env vars, defaults) 
│ │ 
│ ├── models/ # Zod schemas + TypeScript types 
│ │ ├── runbook.ts # Runbook, Step, Dependency schemas 
│ │ ├── inventory.ts # SystemInventory, ServiceHealth schemas 
│ │ ├── report.ts # DRReadinessReport schema 
│ │ └── index.ts # Barrel export 
│ │ 
│ ├── core/ # Business logic 
│ │ ├── parser.ts # Markdown → Runbook (remark AST) 
│ │ ├── validator.ts # Inventory health checker 
│ │ ├── analyzer.ts # Claude LLM analysis orchestrator 
│ │ └── reportFormatter.ts # JSON report → terminal/HTML output 
│ │ 
│ ├── prompts/ # LLM prompt templates (separated from logic) 
│ │ ├── systemPrompt.ts # DR expert system prompt 
│ │ └── analysisPrompt.ts # User prompt builder 
│ │ 
│ ├── api/ # Fastify route handlers 
│ │ ├── routes.ts # Route definitions 
│ │ ├── handlers/ 
│ │ │ ├── analyzeHandler.ts # POST /api/v1/dr/analyze 
│ │ │ └── healthHandler.ts # GET /api/v1/health 
│ │ └── middleware/ 
│ │ └── errorHandler.ts # Global error handler 
│ │ 
│ ├── utils/ 
│ │ ├── logger.ts # Pino logger instance 
│ │ ├── errors.ts # Custom error classes 
│ │ └── timing.ts # Performance timing utility 
│ │ 
│ └── types/ # Shared type declarations 
│ └── index.ts 
│ 
├── mock-data/ # All mock/sample data lives here 
│ ├── runbooks/ 
│ │ ├── estimate-service.md # Happy path — well-structured runbook 
│ │ ├── payment-gateway.md # Edge case — missing steps, vague owners 
│ │ └── auth-service.md # Edge case — RTO impossible to meet 
│ ├── inventories/ 
│ │ ├── healthy.json # All systems UP 
│ │ ├── partial-outage.json # Some systems DOWN 
│ │ └── major-outage.json # Most systems DOWN 
│ └── expected-reports/ # Expected output for snapshot testing 
│ └── estimate-service.json 
│ 
└── tests/ 
 ├── unit/ 
 │ ├── parser.test.ts 
 │ ├── validator.test.ts 
 │ ├── analyzer.test.ts 
 │ └── reportFormatter.test.ts 
 ├── integration/ 
 │ ├── cli.test.ts 
 │ └── api.test.ts 
 └── fixtures/ 
 └── sampleRunbook.md 
 

--- 

## 🔧 Implementation Requirements Per Module 

### A. Config (src/config.ts) 
- Load from environment variables with .env support 
- Zod schema to validate config at startup (fail fast on missing ANTHROPIC_API_KEY) 
- Defaults: PORT=3000, LOG_LEVEL="info", HEALTH_CHECK_TIMEOUT_MS=3000, 
 LLM_MODEL="claude-sonnet-4-20250514", LLM_MAX_TOKENS=4096 

### B. Models (src/models/) 
Define strict Zod schemas with descriptive error messages: 

*Runbook Model:* 
 
- serviceName: string (non-empty) 
- systemOwner: string 
- rtoMinutes: number (positive) 
- rpoMinutes: number (positive) 
- dependencies: array of { name: string, type: enum("database"|"messaging"| 
 "secrets"|"compute"|"network"|"external"|"other"), critical: boolean } 
- steps: array of { 
 stepNumber: number, 
 action: string, 
 owner: string, 
 targetSystem: string (optional), 
 estimatedMinutes: number, 
 validationCommand: string (optional), 
 dependsOn: number[] (step numbers this step depends on — inferred by AI) 
 } 
- rawMarkdown: string (preserve original for reference) 
 

*System Inventory Model:* 
 
- services: array of { 
 name: string, 
 endpoint: string (URL), 
 type: enum("database"|"messaging"|"secrets"|"compute"|"network"|"external"), 
 region: string (optional), 
 expectedStatus: "UP" (default) 
 } 
 

*DR Readiness Report Model:* 
 
- meta: { analyzedAt: ISO datetime, runbookFile: string, inventoryFile: string, 
 agentVersion: string, analysisTimeMs: number } 
- serviceSummary: { name, owner, statedRTO, statedRPO } 
- riskScore: 0-100 
- riskLevel: enum("LOW"|"MEDIUM"|"HIGH"|"CRITICAL") derived from score 
- rtoAnalysis: { 
 feasible: boolean, 
 totalEstimatedMinutes: number, 
 statedRtoMinutes: number, 
 bufferMinutes: number (can be negative), 
 bottleneckSteps: array of step numbers 
 } 
- dependencyHealth: array of { 
 name: string, 
 runbookAssumes: "available", 
 actualStatus: "UP"|"DOWN"|"UNREACHABLE"|"NOT_IN_INVENTORY", 
 impact: string (which steps are affected) 
 } 
- singlePointsOfFailure: array of { 
 description: string, 
 affectedSteps: number[], 
 mitigationSuggestion: string 
 } 
- gapAnalysis: array of { 
 type: enum("MISSING_STEP"|"VAGUE_INSTRUCTION"|"NO_VALIDATION"| 
 "MISSING_ROLLBACK"|"UNVERIFIED_DEPENDENCY"|"OWNER_AMBIGUITY"), 
 description: string, 
 severity: enum("LOW"|"MEDIUM"|"HIGH"), 
 recommendation: string 
 } 
- executionPlan: array of { 
 phase: number, 
 steps: number[] (steps that can run in parallel), 
 estimatedMinutes: number, 
 gate: string (what must be true before proceeding) 
 } 
- suggestions: array of { priority: 1-5, title: string, detail: string } 
- summary: string (2-3 paragraph executive summary readable by non-technical audience) 
 

### C. Markdown Parser (src/core/parser.ts) 
- Use unified().use(remarkParse).parse(markdown) to get MDAST tree 
- Traverse tree to extract: 
 - H1 → service name 
 - Bold text patterns → RTO, RPO, Owner 
 - H2 "Dependencies" section → dependency list 
 - H2 "Recovery Steps" or ordered list → step extraction 
- Use regex patterns as fallback for semi-structured content 
- Handle variations in formatting (bold vs inline code, numbered vs bullet lists) 
- If a field cannot be extracted, populate with sensible defaults and add a 
 parserWarnings: string[] array to the output 
- Return a validated Runbook object via Zod .safeParse() — throw descriptive 
 ParseError if validation fails 

### D. Inventory Validator (src/core/validator.ts) 
- Load inventory JSON and validate with Zod 
- For each service, run parallel health checks using Promise.allSettled + fetch 
 with AbortController timeout 
- *For the PoC, implement a MockHealthChecker* that reads the status from the 
 inventory JSON's mock status field instead of making real HTTP calls 
- Use a strategy pattern: HealthChecker interface with LiveHealthChecker and 
 MockHealthChecker implementations — easy to swap for real integration later 
- Return array of ServiceStatus objects: { name, endpoint, status, latencyMs, error? } 

### E. LLM Analyzer (src/core/analyzer.ts) 
- Use @anthropic-ai/sdk to call Claude 
- *System prompt* (src/prompts/systemPrompt.ts): You are a senior Site Reliability 
 Engineer and Disaster Recovery specialist. Your job is to critically analyze DR 
 runbooks and identify risks, gaps, and improvement opportunities. Be thorough, 
 specific, and actionable. Never say "looks good" — always find at least one 
 improvement even for excellent runbooks. 
- *User prompt* (src/prompts/analysisPrompt.ts): Build structured prompt containing: 
 - Parsed runbook JSON 
 - Validation results JSON 
 - Explicit instructions for each section of the report 
 - Output format specification (JSON matching DRReadinessReport schema) 
- Use Claude's structured output: send response_format or parse JSON from response 
- Validate LLM output against DRReadinessReportSchema with Zod 
- If Zod validation fails, retry once with a correction prompt 
- Add retry logic for API errors (3 retries with exponential backoff) 
- Measure and include analysis time in the report 

### F. Report Formatter (src/core/reportFormatter.ts) 
- formatForTerminal(report): Rich colored terminal output using ANSI codes 
 - Risk score with color coding (green/yellow/orange/red) 
 - Dependency health table 
 - Gap analysis with severity indicators 
 - Executive summary at the top 
- formatAsJSON(report): Pretty-printed JSON 
- formatAsHTML(report): Simple HTML report (for potential future Confluence upload) 

### G. CLI (src/index.ts) 
Commands: 
 
dr-agent analyze --runbook <path> [--inventory <path>] [--format json|terminal|html] 
dr-agent validate --inventory <path> # Only run health checks 
dr-agent parse --runbook <path> # Only parse, no AI analysis 
dr-agent version 
 

- Use commander with typed options 
- Display spinner/progress during LLM analysis (use ora or simple console) 
- Exit codes: 0 = success, 1 = error, 2 = critical risk score (>80) 

### H. REST API (src/server.ts) 
Endpoints: 
 
POST /api/v1/dr/analyze 
 - Body: multipart/form-data with "runbook" file + optional "inventory" file 
 - OR: JSON body with { runbookMarkdown: string, inventory?: object } 
 - Response: DRReadinessReport JSON 

GET /api/v1/dr/analyze 
 - Query: ?runbook=path&inventory=path (file paths on server) 
 - Response: DRReadinessReport JSON 

GET /api/v1/health 
 - Response: { status: "ok", version, uptime } 
 

- Register @fastify/multipart for file uploads 
- Register @fastify/cors for cross-origin 
- Global error handler returning consistent error shape: 
 { error: string, code: string, details?: object } 
- Request logging via pino 
- Graceful shutdown handling 

--- 

## 🎭 Mock Data Strategy 

Since this is a PoC with no real system access, ALL external interactions must be mocked 
but designed for easy real-integration later. 

### Mock Runbooks (create 3 with different characteristics) 

*1. mock-data/runbooks/estimate-service.md* — Well-structured, happy path 
- Clear metadata, 5 ordered steps, specific owners, reasonable time estimates 
- All dependencies listed and present in inventory 
- RTO is achievable 

*2. mock-data/runbooks/payment-gateway.md* — Problematic runbook 
- Vague step descriptions ("fix the database issue") 
- Missing owner for 2 steps (just says "team") 
- One dependency not listed in any inventory 
- No validation/verification steps 
- RTO is very tight (30 min for 45 min of work) 

*3. mock-data/runbooks/auth-service.md* — Critical gaps 
- References deprecated service names 
- Single person named as owner for ALL steps (bus factor = 1) 
- No rollback steps 
- RTO is 15 minutes but steps sum to 60 minutes 
- Missing dependency section entirely 

### Mock Inventories 

*1. healthy.json* — All services UP, low latency 
*2. partial-outage.json* — 2 of 5 services DOWN 
*3. major-outage.json* — 4 of 5 services DOWN, one UNREACHABLE 

### Mock Health Checker 
- Reads status directly from inventory JSON 
- Adds random latency (50-200ms) to simulate real calls 
- Supports a chaos flag that randomly fails 20% of checks 

--- 

## ✅ Testing Strategy 

### Unit Tests (vitest) 
- *parser.test.ts*: Test each runbook variant, verify all fields extracted correctly, 
 test malformed markdown handling, test edge cases (empty file, no headers, etc.) 
- *validator.test.ts*: Mock fetch, test UP/DOWN/UNREACHABLE/timeout scenarios, 
 test parallel execution, verify timeout handling 
- *analyzer.test.ts*: Mock Claude API responses, verify Zod validation of output, 
 test retry logic, test malformed LLM response handling 
- *reportFormatter.test.ts*: Snapshot tests for terminal and HTML output 

### Integration Tests 
- *cli.test.ts*: Spawn CLI process, verify exit codes, verify output format 
- *api.test.ts*: Use Fastify's .inject() for in-process HTTP testing, test all 
 endpoints, test error responses, test file upload 

### Test Coverage Target: >80% 

--- 

## 🚨 Production-Grade Requirements (Non-Negotiable) 

1. *Zero any types* — strict TypeScript throughout 
2. *All errors are typed* — custom error classes extending base AppError 
 (ParseError, ValidationError, AnalysisError, ConfigError) 
3. *Structured logging* — pino with request IDs, correlation IDs 
4. *Graceful degradation* — if LLM fails, still return parser + validator results 
 with a note that AI analysis was unavailable 
5. *Performance tracking* — measure and log time for parsing, validation, LLM call 
6. *Input sanitization* — validate all inputs at API boundary with Zod 
7. *Clean separation of concerns* — no business logic in route handlers, 
 no framework imports in core modules 
8. *Environment-based config* — no hardcoded values 
9. *Proper async/await* — no unhandled promise rejections, proper cleanup 
10. *README.md* — setup instructions, usage examples, architecture overview 

--- 

## 📋 Phased Implementation Plan 

### Phase 1: Foundation 
- Project scaffolding (package.json, tsconfig, eslint, prettier, vitest config) 
- Config module with Zod-validated env loading 
- Logger setup 
- Custom error classes 
- All Zod model definitions 

### Phase 2: Core Parser 
- Markdown parser implementation 
- All 3 mock runbook files 
- Parser unit tests (all variants) 

### Phase 3: Health Validator 
- HealthChecker interface + MockHealthChecker 
- All 3 mock inventory files 
- Validator unit tests 

### Phase 4: LLM Analysis 
- Prompt templates (system + analysis) 
- Claude SDK integration with retry logic 
- Zod validation of LLM output 
- Report formatter (terminal + JSON + HTML) 
- Analyzer unit tests (mocked LLM responses) 

### Phase 5: Interfaces 
- CLI with all commands 
- Fastify REST API with all endpoints 
- Integration tests 

### Phase 6: Polish 
- README with architecture diagram (ASCII) 
- Final test coverage check 
- Lint and format all files 
- End-to-end demo walkthrough in README 

--- 

## ⚠️ Important Instructions for You (Claude) 

1. *Plan first* — Before writing any code, create the complete phased implementation 
 plan. Present it for review. Then proceed phase by phase. 
2. *Ask questions* — If any requirement is ambiguous or you see a better approach, 
 ask before implementing. Especially around: 
 - Markdown parsing edge cases you anticipate 
 - Prompt engineering strategies for consistent structured output 
 - Any architectural decisions you'd approach differently 
3. *Mock everything* — No real API calls, no real system endpoints. But design 
 interfaces so swapping to real implementations requires changing only the 
 dependency injection, not the core logic. 
4. *Test as you go* — Write tests alongside implementation, not after. 
5. *Use Claude API* — The LLM calls use Anthropic's Claude SDK (@anthropic-ai/sdk), 
 not OpenAI. The model is claude-sonnet-4-20250514. 
6. *No shortcuts on error handling* — Every async operation needs proper try/catch, 
 every external input needs Zod validation. 
7. *Keep files focused* — No file should exceed 200 lines. Split if needed. 
8. *ESM only* — Use import/export, file extensions in imports (.js), 
 "type": "module" in package.json.