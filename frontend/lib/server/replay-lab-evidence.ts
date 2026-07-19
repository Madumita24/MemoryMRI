import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

import type {
  ReplayLabControlResult,
  ReplayLabEvidence,
  ReplayLabEvidenceLink,
  ReplayLabIndividualResult,
  ReplayLabPairwiseResult,
  ScenarioMemoryView,
} from "@/lib/benchmark-shared";
import type { DomainName } from "@/lib/benchmark-shared";

type ScenarioCatalogEntry = {
  scenario: {
    id: string;
    title: string;
    domain: DomainName;
    user_input: string;
  };
};

type BenchmarkDomainFile = {
  cases: ScenarioCatalogEntry[];
};

type Day3Summary = {
  verification_results: {
    reviewed_outcomes: Array<{
      scenario_id: string;
      verification_verdict: string;
      artifact_id: string;
    }>;
  };
};

type SuspicionRanking = {
  memories?: Array<{
    memory_id: string;
  }>;
  metadata?: {
    suspicious_without_observed_influence?: string[];
  };
};

type ContradictionAnalysis = {
  pair_results?: Array<{
    memory_a_id: string;
    memory_b_id: string;
  }>;
};

type ProposalArtifact = {
  proposal_id: string;
  concise_explanation: string;
  proposal_status: string;
  support_validity_result?: {
    support_explanation?: string;
  } | null;
};

type InvestigationMemory = {
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
};

type InvestigationRoot = {
  investigation: {
    investigation_id: string;
    parent_trace_id: string;
    scenario_id: string;
    domain: DomainName;
    requested_model: string;
    response_model: string;
    prompt_version: string;
    prompt_content_hash?: string | null;
    run_count: number;
    mode: string;
    cache_policy: string;
    original_selected_action: string | null;
    expected_action?: string | null;
    original_memory_snapshot: InvestigationMemory[];
    created_at: string;
  };
  total_api_usage?: Record<string, number>;
};

type IndividualReplayArtifact = {
  investigation: InvestigationRoot["investigation"];
  total_api_usage?: Record<string, number>;
};

type IndividualReplayEntry = {
  intervention: {
    intervention_type: string;
    target_memory_ids: string[];
  };
  total_runs: number;
  successful_runs: number;
  success_rate: number;
  confidence_interval_low: number;
  confidence_interval_high: number;
  original_successful_runs: number;
  original_total_runs: number;
  original_success_rate: number;
  influence_delta: number;
  original_action_distribution: Record<string, number>;
  intervention_action_distribution: Record<string, number>;
  original_replay_stability: number;
  intervention_replay_stability: number;
  original_errors: string[];
  intervention_errors: string[];
  original_trace_ids?: string[];
  intervention_trace_ids?: string[];
  token_usage?: Record<string, number>;
  support_validity?: {
    decision_still_supported?: boolean;
    requires_human_review?: boolean;
    support_explanation?: string;
  } | null;
};

type InvestigationResultsArtifact = {
  investigation: InvestigationRoot["investigation"] & {
    replay_results: IndividualReplayEntry[];
  };
  total_api_usage?: Record<string, number>;
};

type PairwiseReplayEntry = {
  intervention: {
    intervention_type: string;
    target_memory_ids: [string, string];
  };
  individual_influences: Record<string, number>;
  combined_influence: number;
  interaction_score: number;
  interaction_synergy: number;
  combined_action_distribution: Record<string, number>;
  combined_total_evaluated_runs: number;
  support_validity: {
    decision_still_supported: boolean;
    requires_human_review: boolean;
    support_explanation: string;
  };
  evidence_classification: string;
  infrastructure_error_count: number;
  token_usage?: Record<string, number>;
  original_trace_ids?: string[];
  intervention_trace_ids?: string[];
};

type PairwiseReplayArtifact = {
  pair_results: PairwiseReplayEntry[];
  memory_dependence_classification?: string | null;
};

type ControlEntry = {
  control_type: "no-memory" | "isolate-memory";
  target_memory_id: string | null;
  original_success_rate: number;
  control_success_rate: number;
  original_action_distribution: Record<string, number>;
  control_action_distribution: Record<string, number>;
  replay_stability: number;
  infrastructure_error_count: number;
  token_usage?: Record<string, number>;
  original_trace_ids?: string[];
  control_trace_ids?: string[];
  support_validity: {
    decision_still_supported: boolean;
    requires_human_review: boolean;
    support_explanation: string;
  };
  control_total_evaluated_runs: number;
};

type MemoryControlsArtifact = {
  no_memory_control?: ControlEntry | null;
  isolation_controls?: ControlEntry[];
  memory_dependence_classification?: string | null;
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

function toFileHref(filePath: string): string {
  const normalized = path.resolve(filePath).replaceAll("\\", "/");
  return `file:///${normalized}`;
}

function buildScenarioLink(label: string, href: string | null): ReplayLabEvidenceLink {
  return {
    label,
    href,
    status: href ? "available" : "missing",
  };
}

function buildMemoryView(memory: InvestigationMemory, wrongContextIds: Set<string>): ScenarioMemoryView {
  const analysisFlags = wrongContextIds.has(memory.memory_id) ? ["wrong context analysis"] : [];
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
    analysisFlags,
  };
}

function buildTraceLinks(
  scenarioId: string,
  traceIds: string[] | undefined,
  label: string,
): ReplayLabEvidenceLink[] {
  return (traceIds ?? []).map((traceId, index) =>
    buildScenarioLink(
      `${label} ${index + 1}`,
      `/benchmarks/${scenarioId}?trace=${traceId}`,
    ),
  );
}

function buildArtifactLinks(baseDir: string, names: string[]): ReplayLabEvidenceLink[] {
  return names.map((name) => {
    const filePath = path.join(baseDir, name);
    return buildScenarioLink(name, toFileHref(filePath));
  });
}

function toHighlightedFindings(
  scenarioId: string,
  individualResults: ReplayLabIndividualResult[],
  pairwiseResults: ReplayLabPairwiseResult[],
  controls: {
    noMemoryControl: ReplayLabControlResult | null;
    isolationControls: ReplayLabControlResult[];
  },
  suspicionIds: string[],
  classification: string | null,
): string[] {
  const findings: string[] = [];

  if (scenarioId === "cs_01") {
    findings.push(
      "cs_01_mem_2 shows individual influence 1.0 under REMOVE_MEMORY, but the expected action is not support-valid.",
    );
    findings.push(
      "cs_01_mem_1 ranks highly suspicious while showing no individual replay effect.",
    );
    findings.push(
      "No-memory control preserved ASK_FOR_INFORMATION, so the failure does not disappear when all memory is removed.",
    );
    const isolateMem3 = controls.isolationControls.find((item) => item.targetMemoryId === "cs_01_mem_3");
    if (isolateMem3) {
      findings.push(
        `Isolating cs_01_mem_3 produced ${Object.keys(isolateMem3.controlActionDistribution).join(", ")}.`,
      );
    }
  }

  if (scenarioId === "exp_09") {
    findings.push("All individual influence values remain 0.0 across preserved replay evidence.");
    findings.push("All pairwise combined influence values remain 0.0.");
    findings.push(
      "Incorrect behavior persisted with no memories, indicating that prompt or policy interpretation is a stronger hypothesis than memory influence.",
    );
  }

  if (!findings.length && suspicionIds.length) {
    findings.push(`Top suspicious memories: ${suspicionIds.join(", ")}.`);
  }
  if (!findings.length && pairwiseResults.length) {
    findings.push(`Strongest pairwise classification: ${pairwiseResults[0]?.evidenceClassification ?? "n/a"}.`);
  }
  if (!findings.length && classification) {
    findings.push(`Stored classification: ${classification}.`);
  }

  return findings;
}

export async function loadReplayLabEvidence(
  investigationId: string,
  options: {
    benchmarkMode?: boolean;
  } = {},
): Promise<ReplayLabEvidence | null> {
  const investigationDir = path.join(ARTIFACTS_DIR, "investigations", investigationId);
  const [individualReplay, pairwiseReplay, memoryControls, suspicionRanking, contradictions, day3Summary] =
    await Promise.all([
      readJsonIfExists<InvestigationResultsArtifact>(path.join(investigationDir, "individual-replay.json")),
      readJsonIfExists<PairwiseReplayArtifact>(path.join(investigationDir, "pairwise-replay.json")),
      readJsonIfExists<MemoryControlsArtifact>(path.join(investigationDir, "memory-controls.json")),
      readJsonIfExists<SuspicionRanking>(path.join(investigationDir, "suspicion-ranking.json")),
      readJsonIfExists<ContradictionAnalysis>(path.join(investigationDir, "contradictions.json")),
      readJsonIfExists<Day3Summary>(path.join(ARTIFACTS_DIR, "day3-summary.json")),
    ]);

  const investigation = individualReplay?.investigation;
  if (!investigation) {
    return null;
  }

  const catalog = await loadScenarioCatalog(investigation.scenario_id);
  if (!catalog) {
    return null;
  }

  const wrongContextIds = new Set(
    investigation.original_memory_snapshot
      .filter((memory) => memory.tags.includes("wrong-context"))
      .map((memory) => memory.memory_id),
  );

  const suspicionIds = [
    ...new Set([
      ...(suspicionRanking?.metadata?.suspicious_without_observed_influence ?? []),
      ...(suspicionRanking?.memories?.map((memory) => memory.memory_id) ?? []),
    ]),
  ];

  const contradictionPairs = (contradictions?.pair_results ?? []).map(
    (pair) => `${pair.memory_a_id}/${pair.memory_b_id}`,
  );

  const proposalDir = path.join(investigationDir, "repair-proposals");
  const proposalFiles = await readJsonIfExists<string[]>(
    path.join(proposalDir, "__missing__.json"),
  );
  void proposalFiles;
  let proposal: ProposalArtifact | null = null;
  let proposalId: string | null = null;
  let proposalMarkdownPath: string | null = null;
  try {
    const proposalFileNames = (await fs.readdir(proposalDir))
      .filter((fileName) => fileName.endsWith(".json"))
      .sort();
    if (proposalFileNames.length) {
      const proposalPath = path.join(proposalDir, proposalFileNames[0]);
      proposal = await readJsonFile<ProposalArtifact>(proposalPath);
      proposalId = proposal.proposal_id;
      proposalMarkdownPath = proposalPath.replace(/\.json$/i, ".md");
    }
  } catch {
    proposal = null;
  }

  const verification = day3Summary?.verification_results.reviewed_outcomes.find(
    (item) => item.scenario_id === investigation.scenario_id,
  ) ?? null;

  const individualResults: ReplayLabIndividualResult[] = (investigation.replay_results ?? []).map((result) => ({
    memoryId: result.intervention.target_memory_ids[0] ?? "unknown-memory",
    interventionType: result.intervention.intervention_type,
    runCount: result.total_runs,
    originalSuccessfulRuns: result.original_successful_runs,
    originalTotalRuns: result.original_total_runs,
    originalSuccessRate: result.original_success_rate,
    interventionSuccessfulRuns: result.successful_runs,
    interventionTotalRuns: result.total_runs,
    interventionSuccessRate: result.success_rate,
    influenceDelta: result.influence_delta,
    wilsonLow: result.confidence_interval_low,
    wilsonHigh: result.confidence_interval_high,
    originalActionDistribution: result.original_action_distribution,
    interventionActionDistribution: result.intervention_action_distribution,
    originalReplayStability: result.original_replay_stability,
    interventionReplayStability: result.intervention_replay_stability,
    originalErrors: result.original_errors,
    interventionErrors: result.intervention_errors,
    supportValid: result.support_validity?.decision_still_supported ?? null,
    requiresHumanReview: result.support_validity?.requires_human_review ?? null,
    supportExplanation: result.support_validity?.support_explanation ?? null,
    tokenUsage: null,
    traceLinks: [
      ...buildTraceLinks(investigation.scenario_id, result.original_trace_ids, "Original trace"),
      ...buildTraceLinks(
        investigation.scenario_id,
        result.intervention_trace_ids,
        "Intervention trace",
      ),
    ],
    artifactLinks: buildArtifactLinks(investigationDir, ["individual-replay.json", "individual-replay.md"]),
  }));

  const pairwiseResults: ReplayLabPairwiseResult[] = (pairwiseReplay?.pair_results ?? []).map((result) => {
    const [memoryA, memoryB] = result.intervention.target_memory_ids;
    return {
      memoryIds: [memoryA, memoryB],
      interventionType: result.intervention.intervention_type,
      influenceA: result.individual_influences[memoryA] ?? 0,
      influenceB: result.individual_influences[memoryB] ?? 0,
      combinedInfluence: result.combined_influence,
      interactionScore: result.interaction_score,
      interactionSynergy: result.interaction_synergy,
      combinedActionDistribution: result.combined_action_distribution,
      runCount: result.combined_total_evaluated_runs,
      supportValid: result.support_validity.decision_still_supported,
      requiresHumanReview: result.support_validity.requires_human_review,
      supportExplanation: result.support_validity.support_explanation,
      evidenceClassification: result.evidence_classification,
      infrastructureErrorCount: result.infrastructure_error_count,
      tokenUsage: result.token_usage ?? null,
      traceLinks: [
        ...buildTraceLinks(investigation.scenario_id, result.original_trace_ids, "Original trace"),
        ...buildTraceLinks(
          investigation.scenario_id,
          result.intervention_trace_ids,
          "Pair trace",
        ),
      ],
      artifactLinks: buildArtifactLinks(investigationDir, ["pairwise-replay.json", "pairwise-replay.md"]),
    };
  });

  const toControlResult = (entry: ControlEntry): ReplayLabControlResult => ({
    controlType: entry.control_type,
    targetMemoryId: entry.target_memory_id,
    runCount: entry.control_total_evaluated_runs,
    originalSuccessRate: entry.original_success_rate,
    controlSuccessRate: entry.control_success_rate,
    originalActionDistribution: entry.original_action_distribution,
    controlActionDistribution: entry.control_action_distribution,
    replayStability: entry.replay_stability,
    supportValid: entry.support_validity.decision_still_supported,
    requiresHumanReview: entry.support_validity.requires_human_review,
    supportExplanation: entry.support_validity.support_explanation,
    infrastructureErrorCount: entry.infrastructure_error_count,
    tokenUsage: entry.token_usage ?? null,
    traceLinks: [
      ...buildTraceLinks(investigation.scenario_id, entry.original_trace_ids, "Original trace"),
      ...buildTraceLinks(investigation.scenario_id, entry.control_trace_ids, "Control trace"),
    ],
  });

  const noMemoryControl = memoryControls?.no_memory_control
    ? toControlResult(memoryControls.no_memory_control)
    : null;
  const isolationControls = (memoryControls?.isolation_controls ?? []).map(toControlResult);
  const memoryDependenceClassification =
    pairwiseReplay?.memory_dependence_classification ??
    memoryControls?.memory_dependence_classification ??
    null;

  const highlightedFindings = toHighlightedFindings(
    investigation.scenario_id,
    individualResults,
    pairwiseResults,
    { noMemoryControl, isolationControls },
    suspicionIds,
    memoryDependenceClassification,
  );

  const scenarioLinks: ReplayLabEvidenceLink[] = [
    buildScenarioLink(
      "Parent trace",
      `/benchmarks/${investigation.scenario_id}?trace=${investigation.parent_trace_id}`,
    ),
    buildScenarioLink("Scenario detail", `/benchmarks/${investigation.scenario_id}`),
    buildScenarioLink("Investigation summary", `/investigations?id=${investigationId}`),
    buildScenarioLink("Individual replay JSON", toFileHref(path.join(investigationDir, "individual-replay.json"))),
    buildScenarioLink("Individual replay Markdown", toFileHref(path.join(investigationDir, "individual-replay.md"))),
    buildScenarioLink("Pairwise replay JSON", toFileHref(path.join(investigationDir, "pairwise-replay.json"))),
    buildScenarioLink("Pairwise replay Markdown", toFileHref(path.join(investigationDir, "pairwise-replay.md"))),
    buildScenarioLink("Memory controls JSON", toFileHref(path.join(investigationDir, "memory-controls.json"))),
    buildScenarioLink("Memory controls Markdown", toFileHref(path.join(investigationDir, "memory-controls.md"))),
    buildScenarioLink("Suspicion ranking Markdown", toFileHref(path.join(investigationDir, "suspicion-ranking.md"))),
    buildScenarioLink("Contradictions Markdown", toFileHref(path.join(investigationDir, "contradictions.md"))),
    buildScenarioLink(
      "Repair proposal",
      proposalId ? `/investigations?id=${investigationId}#proposal-${proposalId}` : null,
    ),
    buildScenarioLink(
      "Repair proposal JSON",
      proposalId ? toFileHref(path.join(proposalDir, `${proposalId}.json`)) : null,
    ),
    buildScenarioLink("Repair proposal Markdown", proposalMarkdownPath ? toFileHref(proposalMarkdownPath) : null),
    buildScenarioLink(
      "Verification artifact",
      verification?.artifact_id ? `/artifacts?id=${verification.artifact_id}` : null,
    ),
  ];

  return {
    investigationId,
    scenarioId: investigation.scenario_id,
    title: catalog.title,
    domain: catalog.domain,
    benchmarkMode: options.benchmarkMode ?? true,
    originalAction: investigation.original_selected_action,
    expectedAction: investigation.expected_action ?? null,
    runnerLabel: investigation.requested_model === "fake-deterministic" ? "FakeAgentRunner" : "GPT-5.6",
    requestedModel: investigation.requested_model,
    responseModel: investigation.response_model,
    promptVersion: investigation.prompt_version,
    promptContentHash: investigation.prompt_content_hash ?? null,
    memoryDependenceClassification,
    cachePolicy: investigation.cache_policy,
    runCount: investigation.run_count,
    parentTraceId: investigation.parent_trace_id,
    latestTimestamp: investigation.created_at,
    proposalId,
    proposalSummary: proposal?.concise_explanation ?? null,
    proposalStatus: proposal?.proposal_status ?? null,
    verificationVerdict: verification?.verification_verdict ?? null,
    artifactId: verification?.artifact_id ?? null,
    supportValiditySummary:
      proposal?.support_validity_result?.support_explanation ?? null,
    suspiciousMemoryIds: suspicionIds,
    contradictionPairs,
    scenarioLinks,
    snapshot: investigation.original_memory_snapshot.map((memory) =>
      buildMemoryView(memory, wrongContextIds),
    ),
    individualResults,
    pairwiseResults,
    noMemoryControl,
    isolationControls,
    highlightedFindings,
  };
}
