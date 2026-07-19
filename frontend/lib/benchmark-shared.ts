export type DomainName = "customer_support" | "devops" | "workplace_expense";
export type BenchmarkSourceKey = "gpt" | "fake";

export type BenchmarkScenarioRow = {
  scenarioId: string;
  domain: DomainName;
  title: string;
  memoryCount: number;
  runnerLabel: string;
  actualAction: string;
  expectedAction: string;
  passed: boolean;
  failureCategory: string | null;
  traceId: string;
  investigationId: string | null;
  investigationStatus: string;
  verificationVerdict: string | null;
  artifactId: string | null;
};

export type BenchmarkDomainCard = {
  domain: DomainName;
  label: string;
  scenarioCount: number;
  gptPassCount: number;
  gptFailureCount: number;
  investigationCount: number;
  statusLabel: string;
};

export type BenchmarkSourceEvidence = {
  key: BenchmarkSourceKey;
  label: string;
  runnerType: string;
  model: string | null;
  promptVersion: string;
  artifactSource: string;
  benchmarkId: string;
  timestamp: string;
  overall: {
    attempted: number;
    evaluated: number;
    passed: number;
    failed: number;
    infrastructureErrors: number;
    passRate: number;
  };
  domainResults: Record<
    DomainName,
    {
      attempted: number;
      evaluated: number;
      passed: number;
      failed: number;
      infrastructureErrors: number;
    }
  >;
  categoryResults: Record<
    string,
    {
      attempted: number;
      evaluated: number;
      passed: number;
      failed: number;
      infrastructureErrors: number;
    }
  >;
  scenarioRows: BenchmarkScenarioRow[];
  totalLatencyMs: number | null;
  tokenUsage:
    | {
        inputTokens: number;
        outputTokens: number;
        totalTokens: number;
        billableApiCalls: number;
      }
    | null;
};

export type DashboardFailureCard = {
  scenarioId: string;
  domain: DomainName;
  actualAction: string;
  expectedAction: string;
  investigationId: string | null;
  investigationStatus: string;
  replaySummary: string;
  verificationVerdict: string | null;
  artifactId: string | null;
  memoryDependenceClassification: string | null;
};

export type RecentInvestigation = {
  scenarioId: string;
  domain: DomainName;
  investigationId: string;
  evidenceSummary: string;
  latestProposal: string;
  verdict: string;
};

export type RecentActivity = {
  id: string;
  type: "investigation" | "proposal" | "artifact";
  label: string;
  detail: string;
};

export type DashboardEvidence = {
  title: string;
  description: string;
  gptBaseline: BenchmarkSourceEvidence;
  fakeBaseline: BenchmarkSourceEvidence;
  domainCards: BenchmarkDomainCard[];
  failureCards: DashboardFailureCard[];
  counts: {
    investigations: number;
    proposals: number;
    verificationArtifacts: number;
    newRegressions: number;
  };
  recentInvestigations: RecentInvestigation[];
  recentActivity: RecentActivity[];
  frozenSnapshotTimestamp: string;
};

export type BenchmarkExplorerEvidence = {
  sources: Record<BenchmarkSourceKey, BenchmarkSourceEvidence>;
};

export type ScenarioTraceKind =
  | "official-gpt-baseline"
  | "investigation-replay"
  | "demo-seed"
  | "smoke-test";

export type ScenarioTimelineStep = {
  id: string;
  label: string;
  status: "complete" | "warning" | "error" | "pending";
  detail: string;
  timestamp: string | null;
  evidenceType: "support" | "replay" | "semantic" | "contradiction";
  traceId: string | null;
};

export type ScenarioMemoryView = {
  memoryId: string;
  entityId: string;
  content: string;
  source: string;
  createdAt: string;
  validFrom: string | null;
  validUntil: string | null;
  status: string;
  confidence: number;
  retrievalPriority: number;
  supersedes: string[];
  tags: string[];
  operationalMetadata: Record<string, unknown>;
  analysisFlags: string[];
};

export type ScenarioTraceView = {
  traceId: string;
  scenarioId: string;
  runId: string;
  domain: DomainName;
  userInput: string;
  runnerLabel: string;
  requestedModel: string;
  responseModel: string;
  model: string;
  promptVersion: string;
  promptContentHash: string | null;
  agentInputSchemaVersion: string | null;
  requestHash: string | null;
  retrievedMemoryIds: string[];
  memories: ScenarioMemoryView[];
  selectedAction: string | null;
  actionArguments: Record<string, unknown>;
  citedMemoryIds: string[];
  conciseRationale: string | null;
  uncertainty: number | null;
  needsHumanReview: boolean | null;
  passed: boolean | null;
  executionSource: string;
  cacheLookupLatencyMs: number | null;
  originalModelLatencyMs: number | null;
  latencyMs: number;
  tokenUsage: Record<string, number>;
  requestTokenUsage: Record<string, number> | null;
  cachedOriginalTokenUsage: Record<string, number> | null;
  billableApiCall: boolean;
  cacheEnabled: boolean;
  cacheHit: boolean;
  cachePath: string | null;
  error: {
    code?: string;
    message?: string;
    retryable?: boolean;
    attempts?: number;
  } | null;
  createdAt: string;
  toolCallResponseId: string | null;
  toolCallCacheHit: boolean | null;
  gitCommitHash: string | null;
  timeline: ScenarioTimelineStep[];
  kind: ScenarioTraceKind;
  kindLabel: string;
  sourceLabel: string;
  officialBaseline: boolean;
};

export type ScenarioEvidenceLink = {
  label: string;
  href: string | null;
  status: "available" | "missing";
};

export type ScenarioDetailEvidence = {
  scenarioId: string;
  title: string;
  domain: DomainName;
  benchmarkMode: boolean;
  selectedSource: BenchmarkSourceKey;
  selectedRunnerLabel: string;
  investigationStatus: string;
  verificationVerdict: string | null;
  latestTraceTimestamp: string | null;
  benchmarkEvaluation: {
    benchmarkVersion: string;
    runnerType: string;
    expectedAction: string | null;
    actualAction: string | null;
    passed: boolean | null;
    failureCategory: string | null;
    infrastructureError: string | null;
    evaluatorName: string;
  };
  deterministicComparison: {
    runnerType: string;
    expectedAction: string;
    actualAction: string;
    passed: boolean;
    benchmarkVersion: string;
  } | null;
  selectedTrace: ScenarioTraceView | null;
  traces: ScenarioTraceView[];
  traceNotice: string | null;
  evidenceLinks: ScenarioEvidenceLink[];
};

const DOMAIN_LABELS: Record<DomainName, string> = {
  customer_support: "Customer Support",
  devops: "DevOps Deployment",
  workplace_expense: "Workplace Expense",
};

export function getDomainLabel(domain: DomainName): string {
  return DOMAIN_LABELS[domain];
}

export function toSentenceCase(value: string): string {
  return value.replace(/[_-]+/g, " ");
}
