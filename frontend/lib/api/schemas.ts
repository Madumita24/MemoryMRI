import { z } from "zod";

const domainNameSchema = z.enum([
  "customer_support",
  "devops",
  "workplace_expense",
]);

const memoryStatusSchema = z.enum([
  "active",
  "stale",
  "superseded",
  "uncertain",
  "invalid",
]);

const replayModeSchema = z.enum(["fast", "deep", "custom"]);

const traceCacheStatusSchema = z
  .object({
    enabled: z.boolean(),
    request_hash: z.string().nullable().optional(),
    hit: z.boolean(),
  })
  .passthrough();

const agentInputMemorySchema = z
  .object({
    memory_id: z.string(),
    entity_id: z.string(),
    content: z.string(),
    source: z.string(),
    created_at: z.string(),
    valid_from: z.string().nullable(),
    valid_until: z.string().nullable(),
    status: memoryStatusSchema,
    confidence: z.number(),
    retrieval_priority: z.number(),
    supersedes: z.array(z.string()),
    tags: z.array(z.string()),
    operational_metadata: z.record(z.string(), z.unknown()),
  })
  .strict();

const agentInputSchema = z
  .object({
    schema_version: z.string(),
    scenario_id: z.string(),
    domain: domainNameSchema,
    user_input: z.string(),
    allowed_actions: z.array(z.string()),
    memories: z.array(agentInputMemorySchema),
  })
  .strict();

const structuredAgentResponseSchema = z
  .object({
    selected_action: z.string(),
    action_arguments: z.record(z.string(), z.unknown()),
    cited_memory_ids: z.array(z.string()),
    concise_rationale: z.string(),
    uncertainty: z.number(),
    needs_human_review: z.boolean(),
  })
  .strict();

const replayResultSchema = z
  .object({
    investigation_id: z.string(),
    parent_trace_id: z.string(),
    scenario_id: z.string(),
    total_runs: z.number(),
    successful_runs: z.number(),
    success_rate: z.number(),
    influence_delta: z.number().nullable().optional(),
    mode: replayModeSchema,
  })
  .passthrough();

const publicScenarioSummarySchema = z
  .object({
    scenario_id: z.string(),
    title: z.string(),
    domain: domainNameSchema,
    allowed_actions: z.array(z.string()),
    memory_count: z.number(),
  })
  .strict();

const publicScenarioDetailSchema = z
  .object({
    scenario_id: z.string(),
    title: z.string(),
    domain: domainNameSchema,
    user_input: z.string(),
    allowed_actions: z.array(z.string()),
    memory_ids: z.array(z.string()),
    agent_input: agentInputSchema,
  })
  .strict();

const publicTraceSchema = z
  .object({
    trace_id: z.string(),
    scenario_id: z.string(),
    run_id: z.string(),
    domain: domainNameSchema,
    user_input: z.string(),
    agent_input: agentInputSchema,
    requested_model: z.string(),
    response_model: z.string(),
    model: z.string(),
    prompt_version: z.string(),
    retrieved_memory_ids: z.array(z.string()),
    memory_snapshot: z.array(agentInputMemorySchema),
    structured_response: structuredAgentResponseSchema.nullable().optional(),
    selected_action: z.string().nullable().optional(),
    action_arguments: z.record(z.string(), z.unknown()),
    cited_memory_ids: z.array(z.string()),
    concise_rationale: z.string().nullable().optional(),
    uncertainty: z.number().nullable().optional(),
    needs_human_review: z.boolean().nullable().optional(),
    passed: z.boolean().nullable().optional(),
    execution_source: z.string(),
    cache_lookup_latency_ms: z.number().nullable().optional(),
    original_model_latency_ms: z.number().nullable().optional(),
    latency_ms: z.number(),
    token_usage: z.record(z.string(), z.number()),
    request_token_usage: z.record(z.string(), z.number()).nullable().optional(),
    cached_original_token_usage: z.record(z.string(), z.number()).nullable().optional(),
    billable_api_call: z.boolean(),
    cache: traceCacheStatusSchema,
    parent_trace_id: z.string().nullable().optional(),
    investigation_id: z.string().nullable().optional(),
    replay_role: z.string().nullable().optional(),
    error: z
      .object({
        kind: z.string().optional(),
        message: z.string().optional(),
        retryable: z.boolean().optional(),
        status_code: z.number().optional(),
        details: z.record(z.string(), z.unknown()).optional(),
      })
      .passthrough()
      .nullable()
      .optional(),
    created_at: z.string(),
  })
  .strict();

const publicInvestigationSchema = z
  .object({
    investigation_id: z.string(),
    parent_trace_id: z.string(),
    scenario_id: z.string(),
    domain: domainNameSchema,
    requested_model: z.string(),
    response_model: z.string(),
    prompt_version: z.string(),
    run_count: z.number(),
    mode: replayModeSchema,
    cache_policy: z.string(),
    original_selected_action: z.string().nullable().optional(),
    original_memory_snapshot: z.array(agentInputMemorySchema),
    replay_results: z.array(replayResultSchema),
    created_at: z.string(),
  })
  .strict();

const domainInfoSchema = z
  .object({
    domain: domainNameSchema,
    allowed_actions: z.array(z.string()),
  })
  .strict();

const healthResponseSchema = z
  .object({
    status: z.literal("ok"),
  })
  .strict();

const apiErrorSchema = z
  .object({
    detail: z.union([z.string(), z.record(z.string(), z.unknown())]),
    code: z.string().nullable().optional(),
  })
  .passthrough();

const suspicionRankingSchema = z.object({ metadata: z.record(z.string(), z.unknown()) }).passthrough();
const contradictionAnalysisSchema = z.object({ metadata: z.record(z.string(), z.unknown()).optional() }).passthrough();
const pairwiseReplaySchema = z.object({ metadata: z.record(z.string(), z.unknown()).optional() }).passthrough();
const memoryControlsSchema = z.object({ metadata: z.record(z.string(), z.unknown()).optional() }).passthrough();

const investigationResultsResponseSchema = z
  .object({
    investigation: publicInvestigationSchema,
    suspicion_ranking: suspicionRankingSchema.nullable().optional(),
    contradictions: contradictionAnalysisSchema.nullable().optional(),
    pairwise_replay: pairwiseReplaySchema.nullable().optional(),
    memory_controls: memoryControlsSchema.nullable().optional(),
  })
  .strict();

const repairProposalSchema = z
  .object({
    proposal_id: z.string(),
    investigation_id: z.string(),
    scenario_id: z.string(),
    domain: domainNameSchema,
    repair_type: z.string(),
    target_memory_ids: z.array(z.string()),
    concise_explanation: z.string(),
    confidence: z.number(),
    requires_human_approval: z.boolean(),
    proposal_status: z.string(),
    created_at: z.string(),
    support_validity_result: z
      .object({
        decision_still_supported: z.boolean(),
        outcome_correct: z.boolean(),
        requires_human_review: z.boolean(),
        support_explanation: z.string(),
      })
      .strict(),
  })
  .passthrough();

const memoryDiffSchema = z
  .object({
    diff_id: z.string(),
    proposal_id: z.string().nullable().optional(),
    mode: z.string(),
    target_memory_ids: z.array(z.string()),
    changed_fields: z.array(z.unknown()).optional(),
    unchanged_fields: z.array(z.unknown()).optional(),
    generated_at: z.string(),
  })
  .passthrough();

const verificationRunSchema = z
  .object({
    verification_id: z.string(),
    proposal_id: z.string(),
    scenario_id: z.string(),
    domain: domainNameSchema,
    model: z.string(),
    prompt_version: z.string(),
    repaired_failures: z.array(z.string()),
    persistent_failures: z.array(z.string()),
    new_regressions: z.array(z.string()),
    verdict: z.string(),
    created_at: z.string(),
  })
  .passthrough();

const verificationArtifactSchema = z
  .object({
    artifact_id: z.string(),
    certificate_id: z.string(),
    artifact_version: z.string(),
    investigation_id: z.string(),
    proposal_id: z.string(),
    scenario_id: z.string(),
    domain: domainNameSchema,
    verification_verdict: z.string(),
    expected_action: z.string(),
    original_action: z.string(),
    likely_influential_memories: z.array(z.string()),
    content_hash: z.string(),
    created_at: z.string(),
  })
  .passthrough();

const artifactSummarySchema = z
  .object({
    artifact_id: z.string(),
    certificate_id: z.string(),
    verification_verdict: z.string(),
    scenario_id: z.string(),
    proposal_id: z.string(),
  })
  .strict();

const benchmarkRunResponseSchema = z
  .object({
    run_id: z.string().nullable().optional(),
    summary: z.record(z.string(), z.unknown()),
  })
  .strict();

export const schemas = {
  apiError: apiErrorSchema,
  agentInput: agentInputSchema,
  artifactSummary: artifactSummarySchema,
  benchmarkRunResponse: benchmarkRunResponseSchema,
  domainInfo: domainInfoSchema,
  healthResponse: healthResponseSchema,
  investigationResultsResponse: investigationResultsResponseSchema,
  memoryDiff: memoryDiffSchema,
  publicInvestigation: publicInvestigationSchema,
  publicScenarioDetail: publicScenarioDetailSchema,
  publicScenarioSummary: publicScenarioSummarySchema,
  publicTrace: publicTraceSchema,
  repairProposal: repairProposalSchema,
  verificationArtifact: verificationArtifactSchema,
  verificationRun: verificationRunSchema,
};

export type DomainInfo = z.infer<typeof domainInfoSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type InvestigationResultsResponse = z.infer<typeof investigationResultsResponseSchema>;
export type MemoryDiff = z.infer<typeof memoryDiffSchema>;
export type PublicInvestigation = z.infer<typeof publicInvestigationSchema>;
export type PublicScenarioDetail = z.infer<typeof publicScenarioDetailSchema>;
export type PublicScenarioSummary = z.infer<typeof publicScenarioSummarySchema>;
export type PublicTrace = z.infer<typeof publicTraceSchema>;
export type RepairProposal = z.infer<typeof repairProposalSchema>;
export type ArtifactSummary = z.infer<typeof artifactSummarySchema>;
export type BenchmarkRunResponse = z.infer<typeof benchmarkRunResponseSchema>;
export type VerificationArtifact = z.infer<typeof verificationArtifactSchema>;
export type VerificationRun = z.infer<typeof verificationRunSchema>;
