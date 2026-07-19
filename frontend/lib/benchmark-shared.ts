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
