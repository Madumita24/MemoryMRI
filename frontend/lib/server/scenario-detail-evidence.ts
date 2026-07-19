import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

import type {
  BenchmarkSourceKey,
  MemoryInfluenceContradiction,
  MemoryInfluenceGraphEvidence,
  MemoryInfluenceIndividualReplay,
  MemoryInfluenceMemoryEvidence,
  MemoryInfluencePairwiseInteraction,
  ScenarioDetailEvidence,
  ScenarioEvidenceLink,
  ScenarioMemoryView,
  ScenarioTimelineStep,
  ScenarioTraceKind,
  ScenarioTraceView,
} from "@/lib/benchmark-shared";
import { getDomainLabel, type DomainName } from "@/lib/benchmark-shared";

type ScenarioCatalogEntry = {
  scenario: {
    id: string;
    title: string;
    domain: DomainName;
    user_input: string;
  };
};

type BenchmarkDomainFile = {
  domain: DomainName;
  cases: Array<
    ScenarioCatalogEntry & {
      memories: unknown[];
    }
  >;
};

type Day3Summary = {
  investigations: Array<{
    investigation_id: string;
    scenario_id: string;
    domain: DomainName;
    memory_dependence_classification: string;
  }>;
  proposals: Array<{
    proposal_id: string;
    scenario_id: string;
    repair_type: string;
    proposal_status: string;
  }>;
  verification_results: {
    reviewed_outcomes: Array<{
      scenario_id: string;
      verification_verdict: string;
      artifact_id: string;
    }>;
  };
  artifact_ids: Array<{
    scenario_id: string;
    artifact_id: string;
  }>;
};

type SummaryScenarioRow = {
  scenario_id: string;
  domain?: DomainName;
  trace_id: string;
  expected_action: string;
  actual_selected_action?: string;
  selected_action?: string;
  passed: boolean;
  failure_category?: string;
  error?: string | null;
};

type GptSummary = {
  git_commit_hash: string;
  scenario_results: SummaryScenarioRow[];
};

type FakeSummary = {
  scenario_results: SummaryScenarioRow[];
};

type ArtifactSummary = {
  investigation_id: string;
  proposal_id: string;
  verification_id: string;
};

type VerificationArtifact = {
  scenario_id: string;
  domain: DomainName;
  original_action: string | null;
  expected_action: string | null;
  support_validity_result?: {
    support_explanation?: string;
  } | null;
  individual_replay_evidence?: Array<{
    intervention: {
      intervention_type: string;
      target_memory_ids: string[];
    };
    successful_runs: number;
    total_runs: number;
    success_rate: number;
    influence_delta: number;
    intervention_action_distribution: Record<string, number>;
    support_validity?: {
      decision_still_supported?: boolean;
      requires_human_review?: boolean;
      support_explanation?: string;
    } | null;
  }>;
  pairwise_replay_evidence?: Array<{
    intervention: {
      intervention_type: string;
      target_memory_ids: [string, string];
    };
    combined_influence: number;
    interaction_score: number;
    interaction_synergy: number;
    combined_action_distribution: Record<string, number>;
    support_validity: {
      decision_still_supported: boolean;
      requires_human_review: boolean;
      support_explanation: string;
    };
    evidence_classification: string;
  }>;
  approved_repair?: {
    proposal_id: string | null;
    repair_type: string | null;
    proposal_status: string | null;
    concise_explanation: string | null;
    target_memory_ids: string[];
    before_state?: {
      memory_dependence_classification?: string | null;
    } | null;
    replay_evidence?: {
      no_memory_control_preserved_wrong_action?: boolean;
    } | null;
    suspicion_evidence?: {
      top_ranked_memory_ids?: string[];
      suspicious_without_observed_influence?: string[];
      semantic_hypotheses?: string[];
    } | null;
  } | null;
};

type SuspicionRanking = {
  memories?: Array<{
    memory_id: string;
    semantic_hypothesis?: {
      suspected_issue_types?: string[];
    };
  }>;
};

type ContradictionAnalysis = {
  pair_results?: Array<{
    memory_a_id: string;
    memory_b_id: string;
    deterministic_relationship: {
      relationship: string;
      concise_reason: string;
      confidence: number;
      relevant_fields: string[];
    };
    semantic_relationship: {
      relationship: string;
      concise_explanation: string;
      confidence: number;
      requires_human_review: boolean;
    };
    relationships_agree: boolean;
    pairwise_replay_performed: boolean;
  }>;
};

type StoredTrace = {
  trace_id: string;
  scenario_id: string;
  run_id: string;
  domain: DomainName;
  user_input: string;
  requested_model: string;
  response_model: string;
  model: string;
  prompt_version: string;
  prompt_content_hash?: string | null;
  agent_input_schema_version?: string | null;
  request_hash?: string | null;
  retrieved_memory_ids: string[];
  memory_snapshot: Array<{
    memory_id: string;
    entity_id: string;
    content: string;
    source: string;
    created_at: string;
    valid_from: string | null;
    valid_until: string | null;
    status: string;
    confidence: number;
    retrieval_priority: number;
    supersedes: string[];
    tags: string[];
    operational_metadata: Record<string, unknown>;
  }>;
  selected_action: string | null;
  action_arguments: Record<string, unknown>;
  cited_memory_ids: string[];
  concise_rationale: string | null;
  uncertainty: number | null;
  needs_human_review: boolean | null;
  passed: boolean | null;
  execution_source: string;
  cache_lookup_latency_ms?: number | null;
  original_model_latency_ms?: number | null;
  latency_ms: number;
  token_usage: Record<string, number>;
  request_token_usage?: Record<string, number> | null;
  cached_original_token_usage?: Record<string, number> | null;
  billable_api_call: boolean;
  cache: {
    enabled: boolean;
    request_hash?: string | null;
    hit: boolean;
    cache_path?: string | null;
  };
  error?: {
    code?: string;
    message?: string;
    retryable?: boolean;
    attempts?: number;
  } | null;
  created_at: string;
  tool_call?: {
    response_id?: string | null;
    cache_hit?: boolean | null;
  } | null;
};

type TraceFile = {
  trace: StoredTrace;
  filePath: string;
};

const ROOT_DIR = path.resolve(process.cwd(), "..");
const ARTIFACTS_DIR = path.join(ROOT_DIR, "artifacts");
const BENCHMARK_DATA_DIR = path.join(ROOT_DIR, "benchmark", "data");

async function readJsonFile<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, "utf-8");
  return JSON.parse(raw) as T;
}

async function readJsonIfExists<T>(filePath: string): Promise<T | null> {
  try {
    return await readJsonFile<T>(filePath);
  } catch {
    return null;
  }
}

async function loadScenarioCatalog(scenarioId: string): Promise<{
  title: string;
  domain: DomainName;
  userInput: string;
} | null> {
  const files = await fs.readdir(BENCHMARK_DATA_DIR);

  for (const fileName of files.filter((value) => value.endsWith(".json")).sort()) {
    const payload = await readJsonFile<BenchmarkDomainFile>(path.join(BENCHMARK_DATA_DIR, fileName));
    const match = payload.cases.find((item) => item.scenario.id === scenarioId);
    if (match) {
      return {
        title: match.scenario.title,
        domain: match.scenario.domain,
        userInput: match.scenario.user_input,
      };
    }
  }

  return null;
}

function isWrongContextIssue(issueType: string): boolean {
  return issueType.replace(/[-_]/g, "").toLowerCase() === "wrongcontext";
}

async function loadWrongContextFlags(
  investigationId: string | null,
): Promise<Map<string, string[]>> {
  const flags = new Map<string, string[]>();

  if (!investigationId) {
    return flags;
  }

  const payload = await readJsonIfExists<SuspicionRanking>(
    path.join(ARTIFACTS_DIR, "investigations", investigationId, "suspicion-ranking.json"),
  );

  for (const memory of payload?.memories ?? []) {
    const issues = memory.semantic_hypothesis?.suspected_issue_types ?? [];
    if (issues.some(isWrongContextIssue)) {
      flags.set(memory.memory_id, ["wrong context analysis"]);
    }
  }

  return flags;
}

async function collectInvestigationTraceFiles(investigationId: string): Promise<TraceFile[]> {
  const tracesDir = path.join(ARTIFACTS_DIR, "investigations", investigationId, "traces");

  try {
    const files = await fs.readdir(tracesDir);
    const traceFiles = files.filter((value) => value.endsWith(".json")).sort();
    const results: TraceFile[] = [];

    for (const fileName of traceFiles) {
      const filePath = path.join(tracesDir, fileName);
      const trace = await readJsonFile<StoredTrace>(filePath);
      results.push({ trace, filePath });
    }

    return results;
  } catch {
    return [];
  }
}

function getTraceKind(
  scenarioId: string,
  trace: StoredTrace,
  filePath: string,
  officialGptTraceId: string | null,
): { kind: ScenarioTraceKind; label: string; official: boolean } {
  if (trace.trace_id === officialGptTraceId) {
    return {
      kind: "official-gpt-baseline",
      label: "official frozen GPT baseline",
      official: true,
    };
  }

  if (filePath.includes(`${path.sep}demo-seed${path.sep}`)) {
    return {
      kind: "demo-seed",
      label: "demo seed trace",
      official: false,
    };
  }

  if (filePath.includes("openai-smoke")) {
    return {
      kind: "smoke-test",
      label: "smoke-test trace",
      official: false,
    };
  }

  return {
    kind: "investigation-replay",
    label: trace.scenario_id === scenarioId ? "investigation replay trace" : "related trace",
    official: false,
  };
}

function buildMemoryView(
  memory: StoredTrace["memory_snapshot"][number],
  wrongContextFlags: Map<string, string[]>,
): ScenarioMemoryView {
  return {
    memoryId: memory.memory_id,
    entityId: memory.entity_id,
    content: memory.content,
    source: memory.source,
    createdAt: memory.created_at,
    validFrom: memory.valid_from,
    validUntil: memory.valid_until,
    status: memory.status,
    confidence: memory.confidence,
    retrievalPriority: memory.retrieval_priority,
    supersedes: memory.supersedes,
    tags: memory.tags,
    operationalMetadata: memory.operational_metadata,
    analysisFlags: wrongContextFlags.get(memory.memory_id) ?? [],
  };
}

function buildTimeline(
  trace: StoredTrace,
  investigationId: string | null,
): ScenarioTimelineStep[] {
  const hasError = Boolean(trace.error);
  const evaluationPassed = trace.passed;

  return [
    {
      id: "user-request",
      label: "User request received",
      status: "complete",
      detail: trace.user_input,
      timestamp: trace.created_at,
      evidenceType: "support",
      traceId: trace.trace_id,
    },
    {
      id: "memories-retrieved",
      label: "Memories retrieved",
      status: "complete",
      detail: `${trace.retrieved_memory_ids.length} memories retrieved: ${trace.retrieved_memory_ids.join(", ")}`,
      timestamp: null,
      evidenceType: "replay",
      traceId: trace.trace_id,
    },
    {
      id: "snapshot-constructed",
      label: "Agent-visible snapshot constructed",
      status: "complete",
      detail: `${trace.memory_snapshot.length} memory records serialized for the agent-visible snapshot.`,
      timestamp: null,
      evidenceType: "support",
      traceId: trace.trace_id,
    },
    {
      id: "action-selected",
      label: "Runner selected action",
      status: hasError ? "error" : trace.selected_action ? "complete" : "warning",
      detail: hasError
        ? trace.error?.message ?? "Runner failed before returning an action."
        : trace.selected_action
          ? `${trace.selected_action}${trace.concise_rationale ? ` — ${trace.concise_rationale}` : ""}`
          : "No action was stored for this trace.",
      timestamp: null,
      evidenceType: "support",
      traceId: trace.trace_id,
    },
    {
      id: "tool-call",
      label: "Tool or control action",
      status: trace.tool_call?.response_id || trace.action_arguments ? "complete" : "pending",
      detail: trace.tool_call?.response_id
        ? `OpenAI response ${trace.tool_call.response_id}${trace.tool_call.cache_hit ? " (tool cache hit)" : ""}`
        : Object.keys(trace.action_arguments).length
          ? `Structured action arguments recorded: ${Object.keys(trace.action_arguments).join(", ")}`
          : "No separate tool-call metadata was stored for this trace.",
      timestamp: null,
      evidenceType: "semantic",
      traceId: trace.trace_id,
    },
    {
      id: "evaluator-result",
      label: "Deterministic evaluator result",
      status: hasError ? "error" : evaluationPassed ? "complete" : "warning",
      detail: hasError
        ? "Infrastructure error recorded separately from evaluated benchmark failures."
        : evaluationPassed === null
          ? "No evaluator result was stored."
          : evaluationPassed
            ? "Selected action matched the expected benchmark action."
            : "Selected action differed from the expected benchmark action.",
      timestamp: null,
      evidenceType: "support",
      traceId: trace.trace_id,
    },
    {
      id: "investigation",
      label: "Investigation created when applicable",
      status: investigationId ? "complete" : "pending",
      detail: investigationId
        ? `Investigation ${investigationId} is available for this scenario.`
        : "No stored investigation is linked to this scenario.",
      timestamp: null,
      evidenceType: "contradiction",
      traceId: investigationId,
    },
  ];
}

function deriveFreshnessState(
  memory: StoredTrace["memory_snapshot"][number],
  referenceTime: string,
): string {
  if (memory.status === "invalid") {
    return "invalid";
  }

  if (memory.status === "superseded") {
    return "superseded";
  }

  if (memory.status === "stale") {
    return "stale";
  }

  if (memory.status === "uncertain") {
    return "uncertain";
  }

  if (memory.valid_until && new Date(memory.valid_until).getTime() < new Date(referenceTime).getTime()) {
    return "expired";
  }

  return "active";
}

function parseSemanticHypothesesByMemory(hypotheses: string[] | undefined): Map<string, string[]> {
  const result = new Map<string, string[]>();

  for (const entry of hypotheses ?? []) {
    const [rawMemoryId, ...rest] = entry.split(":");
    const memoryId = rawMemoryId.trim();
    const explanation = rest.join(":").trim();
    if (!memoryId || !explanation) {
      continue;
    }
    const existing = result.get(memoryId) ?? [];
    existing.push(explanation);
    result.set(memoryId, existing);
  }

  return result;
}

function buildDeterministicSuspicionReasons(
  memory: StoredTrace["memory_snapshot"][number],
  contradictionPairs: MemoryInfluenceContradiction[],
  referenceTime: string,
): string[] {
  const reasons: string[] = [];
  const freshness = deriveFreshnessState(memory, referenceTime);

  if (freshness === "stale") {
    reasons.push("Stale status in the operational memory snapshot.");
  }
  if (freshness === "expired") {
    reasons.push("Validity window expired before the selected trace ran.");
  }
  if (freshness === "superseded") {
    reasons.push("Operational metadata marks this memory as superseded.");
  }
  if (memory.supersedes.length) {
    reasons.push(`Supersedes ${memory.supersedes.join(", ")} in metadata.`);
  }
  if (memory.retrieval_priority >= 95) {
    reasons.push("Very high retrieval priority may outweigh more relevant evidence.");
  }
  if (memory.tags.includes("wrong-context")) {
    reasons.push("Tagged as wrong-context in the stored memory metadata.");
  }

  for (const pair of contradictionPairs) {
    if (
      pair.memoryIds.includes(memory.memory_id) &&
      pair.deterministicRelationship.relationship !== "unrelated"
    ) {
      reasons.push(pair.deterministicRelationship.conciseReason);
    }
  }

  return Array.from(new Set(reasons));
}

function groupIndividualReplayByMemory(
  artifact: VerificationArtifact | null,
): Map<string, MemoryInfluenceIndividualReplay[]> {
  const grouped = new Map<string, MemoryInfluenceIndividualReplay[]>();

  for (const item of artifact?.individual_replay_evidence ?? []) {
    const normalized: MemoryInfluenceIndividualReplay = {
      interventionType: item.intervention.intervention_type,
      targetMemoryIds: item.intervention.target_memory_ids,
      successfulRuns: item.successful_runs,
      totalRuns: item.total_runs,
      successRate: item.success_rate,
      influenceDelta: item.influence_delta,
      actionDistribution: item.intervention_action_distribution,
      supportValid: item.support_validity?.decision_still_supported ?? null,
      requiresHumanReview: item.support_validity?.requires_human_review ?? null,
      supportExplanation: item.support_validity?.support_explanation ?? null,
    };

    for (const memoryId of item.intervention.target_memory_ids) {
      const existing = grouped.get(memoryId) ?? [];
      existing.push(normalized);
      grouped.set(memoryId, existing);
    }
  }

  return grouped;
}

function buildPairwiseInteractions(
  artifact: VerificationArtifact | null,
): MemoryInfluencePairwiseInteraction[] {
  return (artifact?.pairwise_replay_evidence ?? []).map((item) => ({
    memoryIds: item.intervention.target_memory_ids,
    interventionType: item.intervention.intervention_type,
    combinedInfluence: item.combined_influence,
    interactionScore: item.interaction_score,
    interactionSynergy: item.interaction_synergy,
    combinedActionDistribution: item.combined_action_distribution,
    supportValid: item.support_validity.decision_still_supported,
    requiresHumanReview: item.support_validity.requires_human_review,
    supportExplanation: item.support_validity.support_explanation,
    evidenceClassification: item.evidence_classification,
  }));
}

function buildContradictions(
  analysis: ContradictionAnalysis | null,
): MemoryInfluenceContradiction[] {
  return (analysis?.pair_results ?? []).map((pair) => ({
    memoryIds: [pair.memory_a_id, pair.memory_b_id],
    deterministicRelationship: {
      relationship: pair.deterministic_relationship.relationship,
      conciseReason: pair.deterministic_relationship.concise_reason,
      confidence: pair.deterministic_relationship.confidence,
      relevantFields: pair.deterministic_relationship.relevant_fields,
    },
    semanticRelationship: {
      relationship: pair.semantic_relationship.relationship,
      conciseExplanation: pair.semantic_relationship.concise_explanation,
      confidence: pair.semantic_relationship.confidence,
      requiresHumanReview: pair.semantic_relationship.requires_human_review,
    },
    relationshipsAgree: pair.relationships_agree,
    pairwiseReplayPerformed: pair.pairwise_replay_performed,
  }));
}

function buildInfluenceGraph(
  selectedTrace: ScenarioTraceView | null,
  artifact: VerificationArtifact | null,
  contradictionAnalysis: ContradictionAnalysis | null,
  suspicionRanking: SuspicionRanking | null,
  domain: DomainName,
): MemoryInfluenceGraphEvidence | null {
  if (!selectedTrace) {
    return null;
  }

  const contradictionPairs = buildContradictions(contradictionAnalysis);
  const pairwiseInteractions = buildPairwiseInteractions(artifact);
  const groupedReplay = groupIndividualReplayByMemory(artifact);
  const semanticHypothesesByMemory = parseSemanticHypothesesByMemory(
    artifact?.approved_repair?.suspicion_evidence?.semantic_hypotheses,
  );
  const rankedMemoryIds = artifact?.approved_repair?.suspicion_evidence?.top_ranked_memory_ids ?? [];
  const suspiciousWithoutInfluence = new Set(
    artifact?.approved_repair?.suspicion_evidence?.suspicious_without_observed_influence ?? [],
  );
  const semanticIssueTypes = new Map(
    (suspicionRanking?.memories ?? []).map((memory) => [
      memory.memory_id,
      memory.semantic_hypothesis?.suspected_issue_types ?? [],
    ]),
  );

  const memories: MemoryInfluenceMemoryEvidence[] = selectedTrace.memories.map((memory) => {
    const replayResults = groupedReplay.get(memory.memoryId) ?? [];
    const pairwiseParticipation = pairwiseInteractions.filter((pair) =>
      pair.memoryIds.includes(memory.memoryId),
    );
    const contradictionRelationships = contradictionPairs.filter((pair) =>
      pair.memoryIds.includes(memory.memoryId),
    );
    const matchingStoredMemory = {
      memory_id: memory.memoryId,
      entity_id: memory.entityId,
      content: memory.content,
      source: memory.source,
      created_at: memory.createdAt,
      valid_from: memory.validFrom,
      valid_until: memory.validUntil,
      status: memory.status,
      confidence: memory.confidence,
      retrieval_priority: memory.retrievalPriority,
      supersedes: memory.supersedes,
      tags: memory.tags,
      operational_metadata: memory.operationalMetadata,
    };
    const strongestIndividualInfluence = replayResults.reduce(
      (best, result) =>
        Math.abs(result.influenceDelta) > Math.abs(best) ? result.influenceDelta : best,
      0,
    );
    const strongestInteractionInfluence = pairwiseParticipation.reduce(
      (best, result) =>
        Math.abs(result.combinedInfluence) > Math.abs(best) ? result.combinedInfluence : best,
      0,
    );

    return {
      memoryId: memory.memoryId,
      shortContent:
        memory.content.length > 84 ? `${memory.content.slice(0, 81).trimEnd()}...` : memory.content,
      content: memory.content,
      status: memory.status,
      freshnessState: deriveFreshnessState(matchingStoredMemory, selectedTrace.createdAt),
      entityId: memory.entityId,
      retrievalPriority: memory.retrievalPriority,
      source: memory.source,
      createdAt: memory.createdAt,
      validFrom: memory.validFrom,
      validUntil: memory.validUntil,
      confidence: memory.confidence,
      supersedes: memory.supersedes,
      tags: memory.tags,
      operationalMetadata: memory.operationalMetadata,
      observedRetrieval: selectedTrace.retrievedMemoryIds.includes(memory.memoryId),
      observedCitation: selectedTrace.citedMemoryIds.includes(memory.memoryId),
      suspicionRank:
        rankedMemoryIds.indexOf(memory.memoryId) >= 0
          ? rankedMemoryIds.indexOf(memory.memoryId) + 1
          : null,
      suspiciousWithoutObservedInfluence: suspiciousWithoutInfluence.has(memory.memoryId),
      deterministicSuspicionReasons: buildDeterministicSuspicionReasons(
        matchingStoredMemory,
        contradictionPairs,
        selectedTrace.createdAt,
      ),
      semanticIssueTypes: semanticIssueTypes.get(memory.memoryId) ?? [],
      semanticHypotheses: semanticHypothesesByMemory.get(memory.memoryId) ?? [],
      semanticSuspicionReasons: memory.analysisFlags,
      strongestIndividualInfluence,
      strongestInteractionInfluence,
      individualReplayResults: replayResults,
      pairwiseParticipation,
      contradictionRelationships,
      proposalTargeted:
        artifact?.approved_repair?.target_memory_ids.includes(memory.memoryId) ?? false,
      supportValidityAudit: [
        ...replayResults
          .map((result) => result.supportExplanation)
          .filter((value): value is string => Boolean(value)),
        ...pairwiseParticipation.map((pair) => pair.supportExplanation),
      ],
    };
  });

  return {
    scenarioId: selectedTrace.scenarioId,
    domain,
    selectedTraceId: selectedTrace.traceId,
    originalAction: artifact?.original_action ?? selectedTrace.selectedAction,
    expectedAction: artifact?.expected_action ?? null,
    classification:
      artifact?.approved_repair?.before_state?.memory_dependence_classification ?? null,
    noMemoryControlPreservedWrongAction:
      artifact?.approved_repair?.replay_evidence?.no_memory_control_preserved_wrong_action ??
      false,
    supportValiditySummary:
      artifact?.support_validity_result?.support_explanation ?? null,
    proposal: artifact?.approved_repair
      ? {
          proposalId: artifact.approved_repair.proposal_id,
          repairType: artifact.approved_repair.repair_type,
          status: artifact.approved_repair.proposal_status,
          conciseExplanation: artifact.approved_repair.concise_explanation,
          targetMemoryIds: artifact.approved_repair.target_memory_ids,
        }
      : null,
    memories,
    pairwiseInteractions,
    contradictions: contradictionPairs,
  };
}

function deriveRunnerLabel(trace: StoredTrace): string {
  if (trace.requested_model === "fake-deterministic" || trace.model.includes("fake")) {
    return "FakeAgentRunner";
  }

  return "GPT-5.6";
}

async function collectTraceFilesForScenario(
  scenarioId: string,
  investigationId: string | null,
): Promise<TraceFile[]> {
  const results: TraceFile[] = [];

  const gptTracePath = path.join(ARTIFACTS_DIR, "gpt-baseline-traces", `${scenarioId}.json`);
  const demoTracePath = path.join(ARTIFACTS_DIR, "demo-seed", "traces", `${scenarioId}-original-trace.json`);
  const smokeTracePath = path.join(ARTIFACTS_DIR, `openai-smoke-${scenarioId}.json`);

  for (const filePath of [gptTracePath, demoTracePath, smokeTracePath]) {
    const trace = await readJsonIfExists<StoredTrace>(filePath);
    if (trace) {
      results.push({ trace, filePath });
    }
  }

  if (investigationId) {
    results.push(...(await collectInvestigationTraceFiles(investigationId)));
  }

  const deduped = new Map<string, TraceFile>();
  for (const item of results) {
    deduped.set(item.trace.trace_id, item);
  }

  return Array.from(deduped.values()).sort((left, right) =>
    left.trace.created_at.localeCompare(right.trace.created_at),
  );
}

function buildEvidenceLinks(
  scenarioId: string,
  investigationId: string | null,
  proposalId: string | null,
  verificationId: string | null,
  artifactId: string | null,
): ScenarioEvidenceLink[] {
  return [
    {
      label: "Investigation",
      href: investigationId ? `/investigations?id=${investigationId}` : null,
      status: investigationId ? "available" : "missing",
    },
    {
      label: "Individual replay",
      href: investigationId ? `/investigations?id=${investigationId}#individual-replay` : null,
      status: investigationId ? "available" : "missing",
    },
    {
      label: "Suspicion analysis",
      href: investigationId ? `/investigations?id=${investigationId}#suspicion-ranking` : null,
      status: investigationId ? "available" : "missing",
    },
    {
      label: "Contradictions",
      href: investigationId ? `/investigations?id=${investigationId}#contradictions` : null,
      status: investigationId ? "available" : "missing",
    },
    {
      label: "Pairwise replay",
      href: investigationId ? `/investigations?id=${investigationId}#pairwise-replay` : null,
      status: investigationId ? "available" : "missing",
    },
    {
      label: "Repair proposal",
      href:
        investigationId && proposalId
          ? `/investigations?id=${investigationId}#proposal-${proposalId}`
          : null,
      status: investigationId && proposalId ? "available" : "missing",
    },
    {
      label: "Verification artifact",
      href: artifactId ? `/artifacts?id=${artifactId}` : null,
      status: artifactId ? "available" : "missing",
    },
    {
      label: "Verification record",
      href: verificationId ? `/verification?id=${verificationId}` : null,
      status: verificationId ? "available" : "missing",
    },
    {
      label: "Back to benchmark explorer",
      href: `/benchmarks?source=gpt&query=${scenarioId}`,
      status: "available",
    },
  ];
}

export async function loadScenarioDetailEvidence(
  scenarioId: string,
  options: {
    source?: string;
    traceId?: string;
  } = {},
): Promise<ScenarioDetailEvidence | null> {
  const catalog = await loadScenarioCatalog(scenarioId);
  if (!catalog) {
    return null;
  }

  const [gptSummary, fakeSummary, day3Summary] = await Promise.all([
    readJsonFile<GptSummary>(path.join(ARTIFACTS_DIR, "gpt-baseline-summary.json")),
    readJsonFile<FakeSummary>(path.join(ARTIFACTS_DIR, "day1-mixed-baseline-summary.json")),
    readJsonFile<Day3Summary>(path.join(ARTIFACTS_DIR, "day3-summary.json")),
  ]);

  const gptRow = gptSummary.scenario_results.find((item) => item.scenario_id === scenarioId) ?? null;
  const fakeRow = fakeSummary.scenario_results.find((item) => item.scenario_id === scenarioId) ?? null;
  const investigation = day3Summary.investigations.find((item) => item.scenario_id === scenarioId) ?? null;
  const proposal = day3Summary.proposals.find((item) => item.scenario_id === scenarioId) ?? null;
  const verification = day3Summary.verification_results.reviewed_outcomes.find(
    (item) => item.scenario_id === scenarioId,
  ) ?? null;
  const artifactRef = day3Summary.artifact_ids.find((item) => item.scenario_id === scenarioId) ?? null;
  const artifact = artifactRef
    ? await readJsonIfExists<ArtifactSummary>(
        path.join(ARTIFACTS_DIR, "verification-artifacts", `${artifactRef.artifact_id}.json`),
      )
    : null;

  const selectedSource = options.source === "fake" ? "fake" : "gpt";
  const wrongContextFlags = await loadWrongContextFlags(investigation?.investigation_id ?? null);
  const traceFiles = await collectTraceFilesForScenario(
    scenarioId,
    investigation?.investigation_id ?? null,
  );

  const traces: ScenarioTraceView[] = traceFiles.map(({ trace, filePath }) => {
    const traceKind = getTraceKind(scenarioId, trace, filePath, gptRow?.trace_id ?? null);
    return {
      traceId: trace.trace_id,
      scenarioId: trace.scenario_id,
      runId: trace.run_id,
      domain: trace.domain,
      userInput: trace.user_input,
      runnerLabel: deriveRunnerLabel(trace),
      requestedModel: trace.requested_model,
      responseModel: trace.response_model,
      model: trace.model,
      promptVersion: trace.prompt_version,
      promptContentHash: trace.prompt_content_hash ?? null,
      agentInputSchemaVersion: trace.agent_input_schema_version ?? null,
      requestHash: trace.request_hash ?? trace.cache.request_hash ?? null,
      retrievedMemoryIds: trace.retrieved_memory_ids,
      memories: trace.memory_snapshot.map((memory) => buildMemoryView(memory, wrongContextFlags)),
      selectedAction: trace.selected_action,
      actionArguments: trace.action_arguments,
      citedMemoryIds: trace.cited_memory_ids,
      conciseRationale: trace.concise_rationale,
      uncertainty: trace.uncertainty,
      needsHumanReview: trace.needs_human_review,
      passed: trace.passed,
      executionSource: trace.execution_source,
      cacheLookupLatencyMs: trace.cache_lookup_latency_ms ?? null,
      originalModelLatencyMs: trace.original_model_latency_ms ?? null,
      latencyMs: trace.latency_ms,
      tokenUsage: trace.token_usage,
      requestTokenUsage: trace.request_token_usage ?? null,
      cachedOriginalTokenUsage: trace.cached_original_token_usage ?? null,
      billableApiCall: trace.billable_api_call,
      cacheEnabled: trace.cache.enabled,
      cacheHit: trace.cache.hit,
      cachePath: trace.cache.cache_path ?? null,
      error: trace.error ?? null,
      createdAt: trace.created_at,
      toolCallResponseId: trace.tool_call?.response_id ?? null,
      toolCallCacheHit: trace.tool_call?.cache_hit ?? null,
      gitCommitHash: traceKind.official ? gptSummary.git_commit_hash : null,
      timeline: buildTimeline(trace, investigation?.investigation_id ?? null),
      kind: traceKind.kind,
      kindLabel: traceKind.label,
      sourceLabel: path.relative(ROOT_DIR, filePath).replaceAll("\\", "/"),
      officialBaseline: traceKind.official,
    };
  });

  const selectedTrace =
    traces.find((trace) => trace.traceId === options.traceId) ??
    traces.find((trace) => trace.officialBaseline) ??
    traces[0] ??
    null;

  const latestTraceTimestamp = traces.length
    ? traces[traces.length - 1].createdAt
    : null;

  const evaluationSource = selectedSource === "fake" ? fakeRow : gptRow;
  const benchmarkEvaluation = {
    benchmarkVersion:
      selectedSource === "fake"
        ? "day1-mixed-baseline-summary.json"
        : "gpt-baseline-summary.json",
    runnerType: selectedSource === "fake" ? "FakeAgentRunner" : "OpenAIAgentRunner",
    expectedAction: evaluationSource?.expected_action ?? null,
    actualAction:
      evaluationSource?.actual_selected_action ??
      evaluationSource?.selected_action ??
      selectedTrace?.selectedAction ??
      null,
    passed: evaluationSource?.passed ?? selectedTrace?.passed ?? null,
    failureCategory: gptRow?.failure_category ?? null,
    infrastructureError: selectedTrace?.error?.message ?? null,
    evaluatorName: "deterministic benchmark evaluator",
  };

  const deterministicComparison =
    fakeRow && selectedSource === "gpt"
      ? {
          runnerType: "FakeAgentRunner",
          expectedAction: fakeRow.expected_action,
          actualAction: fakeRow.selected_action ?? fakeRow.actual_selected_action ?? "unknown",
          passed: fakeRow.passed,
          benchmarkVersion: "day1-mixed-baseline-summary.json",
        }
      : null;

  const traceNotice =
    selectedSource === "fake" && selectedTrace?.runnerLabel !== "FakeAgentRunner"
      ? "The frozen deterministic baseline stores summary results for this scenario, but no full fake-runner execution trace artifact is committed. The observable trace below is the nearest stored execution trace."
      : null;

  const fullArtifact = artifactRef
    ? await readJsonIfExists<VerificationArtifact>(
        path.join(ARTIFACTS_DIR, "verification-artifacts", `${artifactRef.artifact_id}.json`),
      )
    : null;
  const suspicionRanking = investigation?.investigation_id
    ? await readJsonIfExists<SuspicionRanking>(
        path.join(ARTIFACTS_DIR, "investigations", investigation.investigation_id, "suspicion-ranking.json"),
      )
    : null;
  const contradictionAnalysis = investigation?.investigation_id
    ? await readJsonIfExists<ContradictionAnalysis>(
        path.join(ARTIFACTS_DIR, "investigations", investigation.investigation_id, "contradictions.json"),
      )
    : null;

  return {
    scenarioId,
    title: catalog.title,
    domain: catalog.domain,
    benchmarkMode: true,
    selectedSource,
    selectedRunnerLabel: selectedSource === "fake" ? "FakeAgentRunner" : "GPT-5.6",
    investigationStatus: investigation ? "investigated" : "not investigated",
    verificationVerdict: verification?.verification_verdict ?? null,
    latestTraceTimestamp,
    benchmarkEvaluation,
    deterministicComparison,
    selectedTrace,
    traces,
    traceNotice,
    influenceGraph: buildInfluenceGraph(
      selectedTrace,
      fullArtifact,
      contradictionAnalysis,
      suspicionRanking,
      catalog.domain,
    ),
    evidenceLinks: buildEvidenceLinks(
      scenarioId,
      investigation?.investigation_id ?? null,
      proposal?.proposal_id ?? artifact?.proposal_id ?? null,
      artifact?.verification_id ?? null,
      artifactRef?.artifact_id ?? null,
    ),
  };
}
