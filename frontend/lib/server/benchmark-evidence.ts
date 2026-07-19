import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";
import type {
  BenchmarkDomainCard,
  BenchmarkExplorerEvidence,
  BenchmarkScenarioRow,
  BenchmarkSourceEvidence,
  DashboardEvidence,
  DashboardFailureCard,
  DomainName,
  RecentActivity,
  RecentInvestigation,
} from "@/lib/benchmark-shared";
import { getDomainLabel, toSentenceCase } from "@/lib/benchmark-shared";

type BenchmarkCatalogCase = {
  scenario: {
    id: string;
    title: string;
    domain: DomainName;
    allowed_actions: string[];
  };
  memories: unknown[];
};

type BenchmarkDomainFile = {
  domain: DomainName;
  cases: BenchmarkCatalogCase[];
};

type GptScenarioResult = {
  scenario_id: string;
  domain: DomainName;
  failure_category: string;
  expected_action: string;
  actual_selected_action: string;
  passed: boolean;
  cache_status: boolean;
  trace_id: string;
};

type GptSummary = {
  model: string;
  prompt_versions: Record<DomainName, string>;
  timestamp: string;
  overall: {
    attempted_scenarios: number;
    evaluated_scenarios: number;
    passed_scenarios: number;
    failed_scenarios: number;
    infrastructure_errors: number;
    pass_rate: number;
  };
  results_by_domain: Record<
    DomainName,
    {
      attempted: number;
      evaluated: number;
      passed: number;
      failed: number;
      infrastructure_errors: number;
    }
  >;
  results_by_failure_category: Record<
    string,
    {
      attempted: number;
      evaluated: number;
      passed: number;
      failed: number;
      infrastructure_errors: number;
    }
  >;
  scenario_results: GptScenarioResult[];
  totals: {
    total_latency_ms: number;
    request_token_usage: {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    };
    billable_api_calls: number;
  };
};

type FakeScenarioResult = {
  scenario_id: string;
  selected_action: string;
  expected_action: string;
  passed: boolean;
  trace_id: string;
  error: string | null;
};

type FakeSummary = {
  total_scenarios: number;
  passed_scenarios: number;
  failed_scenarios: number;
  results_by_domain: Record<
    DomainName,
    {
      total: number;
      passed: number;
      failed: number;
    }
  >;
  results_by_failure_category: Record<
    string,
    {
      total: number;
      passed: number;
      failed: number;
    }
  >;
  scenario_results: FakeScenarioResult[];
};

type Day3Summary = {
  generated_at: string;
  investigations: Array<{
    investigation_id: string;
    scenario_id: string;
    domain: DomainName;
    memory_dependence_classification: string;
    outcome: string;
  }>;
  proposals: Array<{
    proposal_id: string;
    scenario_id: string;
    repair_type: string;
    proposal_status: string;
    outcome: string;
  }>;
  verification_results: {
    reviewed_outcomes: Array<{
      scenario_id: string;
      artifact_id: string;
      verification_verdict: string;
      regressions: string[];
    }>;
  };
  artifact_ids: Array<{
    artifact_id: string;
    scenario_id: string;
    fingerprint: string;
  }>;
};

type Day3DemoSummary = {
  selected_demo_outcome: string;
  cs_01: {
    investigation_id: string;
    proposal_id: string;
    proposal_repair_type: string;
    proposal_status: string;
    support_validity_result: {
      support_explanation: string;
    };
    verification_verdict: string;
    artifact_id: string;
    blocked_reason: string;
  };
  exp_09: {
    original_trace?: {
      selected_action: string;
      expected_action: string;
    };
    investigation_id?: string;
    memory_dependence_classification?: string;
    support_validity_result?: {
      support_explanation: string;
    };
    verification_verdict?: string;
    artifact?: {
      artifact_id: string;
    };
    proposal?: {
      support_validity_result?: {
        support_explanation: string;
      };
    };
    artifact_summary?: {
      memory_dependence_classification?: string;
      verification_verdict?: string;
      artifact_id?: string;
      support_validity_result?: {
        support_explanation: string;
      };
    };
  };
};

const ROOT_DIR = path.resolve(process.cwd(), "..");
const ARTIFACTS_DIR = path.join(ROOT_DIR, "artifacts");
const BENCHMARK_DATA_DIR = path.join(ROOT_DIR, "benchmark", "data");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function readJsonFile<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, "utf-8");
  return JSON.parse(raw) as T;
}

async function loadScenarioCatalog(): Promise<
  Map<string, { title: string; domain: DomainName; memoryCount: number }>
> {
  const files = await fs.readdir(BENCHMARK_DATA_DIR);
  const catalog = new Map<string, { title: string; domain: DomainName; memoryCount: number }>();

  for (const fileName of files.filter((value) => value.endsWith(".json")).sort()) {
    const payload = await readJsonFile<BenchmarkDomainFile>(path.join(BENCHMARK_DATA_DIR, fileName));
    for (const entry of payload.cases) {
      catalog.set(entry.scenario.id, {
        title: entry.scenario.title,
        domain: entry.scenario.domain,
        memoryCount: entry.memories.length,
      });
    }
  }

  return catalog;
}

function buildPromptVersionLabel(promptVersions: Record<DomainName, string>): string {
  return (Object.entries(promptVersions) as Array<[DomainName, string]>)
    .map(([domain, version]) => `${domain}:${version}`)
    .join(" | ");
}

function buildInvestigationMaps(day3Summary: Day3Summary) {
  const investigationByScenario = new Map(day3Summary.investigations.map((item) => [item.scenario_id, item]));
  const proposalByScenario = new Map(day3Summary.proposals.map((item) => [item.scenario_id, item]));
  const verificationByScenario = new Map(
    day3Summary.verification_results.reviewed_outcomes.map((item) => [item.scenario_id, item]),
  );
  const artifactByScenario = new Map(day3Summary.artifact_ids.map((item) => [item.scenario_id, item]));

  return {
    artifactByScenario,
    investigationByScenario,
    proposalByScenario,
    verificationByScenario,
  };
}

async function loadFakeTimestamp(): Promise<string> {
  const stats = await fs.stat(path.join(ARTIFACTS_DIR, "day1-mixed-baseline-summary.json"));
  return stats.mtime.toISOString();
}

function buildGptSource(
  summary: GptSummary,
  catalog: Map<string, { title: string; domain: DomainName; memoryCount: number }>,
  day3Summary: Day3Summary,
): BenchmarkSourceEvidence {
  const maps = buildInvestigationMaps(day3Summary);

  return {
    key: "gpt",
    label: "Official GPT baseline",
    runnerType: "OpenAIAgentRunner",
    model: summary.model,
    promptVersion: buildPromptVersionLabel(summary.prompt_versions),
    artifactSource: "artifacts/gpt-baseline-summary.json",
    benchmarkId: "artifacts/gpt-baseline-summary.json",
    timestamp: summary.timestamp,
    overall: {
      attempted: summary.overall.attempted_scenarios,
      evaluated: summary.overall.evaluated_scenarios,
      passed: summary.overall.passed_scenarios,
      failed: summary.overall.failed_scenarios,
      infrastructureErrors: summary.overall.infrastructure_errors,
      passRate: summary.overall.pass_rate,
    },
    domainResults: Object.fromEntries(
      (Object.entries(summary.results_by_domain) as Array<
        [DomainName, GptSummary["results_by_domain"][DomainName]]
      >).map(([domain, result]) => [
        domain,
        {
          attempted: result.attempted,
          evaluated: result.evaluated,
          passed: result.passed,
          failed: result.failed,
          infrastructureErrors: result.infrastructure_errors,
        },
      ]),
    ) as BenchmarkSourceEvidence["domainResults"],
    categoryResults: Object.fromEntries(
      Object.entries(summary.results_by_failure_category).map(([category, result]) => [
        category,
        {
          attempted: result.attempted,
          evaluated: result.evaluated,
          passed: result.passed,
          failed: result.failed,
          infrastructureErrors: result.infrastructure_errors,
        },
      ]),
    ),
    scenarioRows: summary.scenario_results.map((scenario) => {
      const catalogEntry = catalog.get(scenario.scenario_id);
      const investigation = maps.investigationByScenario.get(scenario.scenario_id);
      const verification = maps.verificationByScenario.get(scenario.scenario_id);
      const artifact = maps.artifactByScenario.get(scenario.scenario_id);

      return {
        scenarioId: scenario.scenario_id,
        domain: scenario.domain,
        title: catalogEntry?.title ?? scenario.scenario_id,
        memoryCount: catalogEntry?.memoryCount ?? 0,
        runnerLabel: "GPT-5.6",
        actualAction: scenario.actual_selected_action,
        expectedAction: scenario.expected_action,
        passed: scenario.passed,
        failureCategory: scenario.failure_category,
        traceId: scenario.trace_id,
        investigationId: investigation?.investigation_id ?? null,
        investigationStatus: investigation ? "investigated" : "not investigated",
        verificationVerdict: verification?.verification_verdict ?? null,
        artifactId: artifact?.artifact_id ?? null,
      };
    }),
    totalLatencyMs: summary.totals.total_latency_ms,
    tokenUsage: {
      inputTokens: summary.totals.request_token_usage.input_tokens,
      outputTokens: summary.totals.request_token_usage.output_tokens,
      totalTokens: summary.totals.request_token_usage.total_tokens,
      billableApiCalls: summary.totals.billable_api_calls,
    },
  };
}

async function buildFakeSource(
  summary: FakeSummary,
  catalog: Map<string, { title: string; domain: DomainName; memoryCount: number }>,
  day3Summary: Day3Summary,
): Promise<BenchmarkSourceEvidence> {
  const maps = buildInvestigationMaps(day3Summary);

  return {
    key: "fake",
    label: "Deterministic fake baseline",
    runnerType: "FakeAgentRunner",
    model: null,
    promptVersion: "n/a (deterministic heuristics)",
    artifactSource: "artifacts/day1-mixed-baseline-summary.json",
    benchmarkId: "artifacts/day1-mixed-baseline-summary.json",
    timestamp: await loadFakeTimestamp(),
    overall: {
      attempted: summary.total_scenarios,
      evaluated: summary.total_scenarios,
      passed: summary.passed_scenarios,
      failed: summary.failed_scenarios,
      infrastructureErrors: 0,
      passRate: summary.passed_scenarios / summary.total_scenarios,
    },
    domainResults: Object.fromEntries(
      (Object.entries(summary.results_by_domain) as Array<
        [DomainName, FakeSummary["results_by_domain"][DomainName]]
      >).map(([domain, result]) => [
        domain,
        {
          attempted: result.total,
          evaluated: result.total,
          passed: result.passed,
          failed: result.failed,
          infrastructureErrors: 0,
        },
      ]),
    ) as BenchmarkSourceEvidence["domainResults"],
    categoryResults: Object.fromEntries(
      Object.entries(summary.results_by_failure_category).map(([category, result]) => [
        category,
        {
          attempted: result.total,
          evaluated: result.total,
          passed: result.passed,
          failed: result.failed,
          infrastructureErrors: 0,
        },
      ]),
    ),
    scenarioRows: summary.scenario_results.map((scenario) => {
      const catalogEntry = catalog.get(scenario.scenario_id);
      const investigation = maps.investigationByScenario.get(scenario.scenario_id);
      const verification = maps.verificationByScenario.get(scenario.scenario_id);
      const artifact = maps.artifactByScenario.get(scenario.scenario_id);

      return {
        scenarioId: scenario.scenario_id,
        domain: catalogEntry?.domain ?? "customer_support",
        title: catalogEntry?.title ?? scenario.scenario_id,
        memoryCount: catalogEntry?.memoryCount ?? 0,
        runnerLabel: "FakeAgentRunner",
        actualAction: scenario.selected_action,
        expectedAction: scenario.expected_action,
        passed: scenario.passed,
        failureCategory: null,
        traceId: scenario.trace_id,
        investigationId: investigation?.investigation_id ?? null,
        investigationStatus: investigation ? "investigated" : "not investigated",
        verificationVerdict: verification?.verification_verdict ?? null,
        artifactId: artifact?.artifact_id ?? null,
      };
    }),
    totalLatencyMs: null,
    tokenUsage: null,
  };
}

function buildDomainCards(gptSource: BenchmarkSourceEvidence, day3Summary: Day3Summary): BenchmarkDomainCard[] {
  const investigationsByDomain = day3Summary.investigations.reduce<Record<DomainName, number>>(
    (accumulator, item) => {
      accumulator[item.domain] += 1;
      return accumulator;
    },
    {
      customer_support: 0,
      devops: 0,
      workplace_expense: 0,
    },
  );

  return (Object.keys(gptSource.domainResults) as DomainName[]).map((domain) => {
    const result = gptSource.domainResults[domain];
      return {
        domain,
        label: getDomainLabel(domain),
        scenarioCount: result.attempted,
        gptPassCount: result.passed,
        gptFailureCount: result.failed,
        investigationCount: investigationsByDomain[domain],
        statusLabel: result.failed === 0 ? "all passing in frozen GPT run" : `${result.failed} frozen GPT failure`,
    };
  });
}

function buildFailureCards(
  gptSource: BenchmarkSourceEvidence,
  day3Summary: Day3Summary,
  demoSummary: Day3DemoSummary,
): DashboardFailureCard[] {
  const maps = buildInvestigationMaps(day3Summary);
  const scenarioLookup = new Map(gptSource.scenarioRows.map((row) => [row.scenarioId, row]));

  const cs01 = scenarioLookup.get("cs_01");
  const exp09 = scenarioLookup.get("exp_09");

  if (!cs01 || !exp09) {
    return [];
  }

  const exp09ReplaySummary =
    demoSummary.exp_09.support_validity_result?.support_explanation ??
    demoSummary.exp_09.proposal?.support_validity_result?.support_explanation ??
    demoSummary.exp_09.artifact_summary?.support_validity_result?.support_explanation ??
    "Replay evidence did not justify a memory edit and the issue remained memory-independent.";
  const exp09Verdict =
    demoSummary.exp_09.verification_verdict ??
    demoSummary.exp_09.artifact_summary?.verification_verdict ??
    maps.verificationByScenario.get("exp_09")?.verification_verdict ??
    null;
  const exp09ArtifactId =
    demoSummary.exp_09.artifact?.artifact_id ??
    demoSummary.exp_09.artifact_summary?.artifact_id ??
    maps.artifactByScenario.get("exp_09")?.artifact_id ??
    null;
  const exp09MemoryDependence =
    demoSummary.exp_09.memory_dependence_classification ??
    demoSummary.exp_09.artifact_summary?.memory_dependence_classification ??
    maps.investigationByScenario.get("exp_09")?.memory_dependence_classification ??
    null;

  return [
    {
      scenarioId: cs01.scenarioId,
      domain: cs01.domain,
      actualAction: cs01.actualAction,
      expectedAction: cs01.expectedAction,
      investigationId: maps.investigationByScenario.get("cs_01")?.investigation_id ?? null,
      investigationStatus: cs01.investigationStatus,
      replaySummary: demoSummary.cs_01.support_validity_result.support_explanation,
      verificationVerdict: demoSummary.cs_01.verification_verdict,
      artifactId: demoSummary.cs_01.artifact_id,
      memoryDependenceClassification:
        maps.investigationByScenario.get("cs_01")?.memory_dependence_classification ?? null,
    },
    {
      scenarioId: exp09.scenarioId,
      domain: exp09.domain,
      actualAction: exp09.actualAction,
      expectedAction: exp09.expectedAction,
      investigationId:
        demoSummary.exp_09.investigation_id ??
        maps.investigationByScenario.get("exp_09")?.investigation_id ??
        null,
      investigationStatus: exp09.investigationStatus,
      replaySummary: exp09ReplaySummary,
      verificationVerdict: exp09Verdict,
      artifactId: exp09ArtifactId,
      memoryDependenceClassification: exp09MemoryDependence,
    },
  ];
}

function buildRecentInvestigations(day3Summary: Day3Summary): RecentInvestigation[] {
  const maps = buildInvestigationMaps(day3Summary);

  return day3Summary.investigations.map((investigation) => ({
    scenarioId: investigation.scenario_id,
    domain: investigation.domain,
    investigationId: investigation.investigation_id,
    evidenceSummary: investigation.memory_dependence_classification,
    latestProposal:
      maps.proposalByScenario.get(investigation.scenario_id)?.repair_type ?? "no proposal yet",
    verdict:
      maps.verificationByScenario.get(investigation.scenario_id)?.verification_verdict ??
      "not verified",
  }));
}

function buildRecentActivity(day3Summary: Day3Summary): RecentActivity[] {
  const activities: RecentActivity[] = [];

  for (const investigation of day3Summary.investigations) {
    activities.push({
      id: investigation.investigation_id,
      type: "investigation",
      label: `${investigation.scenario_id} investigation`,
      detail: investigation.memory_dependence_classification,
    });
  }

  for (const proposal of day3Summary.proposals) {
    activities.push({
      id: proposal.proposal_id,
      type: "proposal",
      label: `${proposal.scenario_id} proposal`,
      detail: `${proposal.repair_type} • ${proposal.proposal_status}`,
    });
  }

  for (const artifact of day3Summary.artifact_ids) {
    activities.push({
      id: artifact.artifact_id,
      type: "artifact",
      label: `${artifact.scenario_id} artifact`,
      detail: artifact.fingerprint,
    });
  }

  return activities;
}

export async function loadDashboardEvidence(): Promise<DashboardEvidence> {
  const [catalog, gptSummary, fakeSummary, day3Summary, demoSummary] = await Promise.all([
    loadScenarioCatalog(),
    readJsonFile<GptSummary>(path.join(ARTIFACTS_DIR, "gpt-baseline-summary.json")),
    readJsonFile<FakeSummary>(path.join(ARTIFACTS_DIR, "day1-mixed-baseline-summary.json")),
    readJsonFile<Day3Summary>(path.join(ARTIFACTS_DIR, "day3-summary.json")),
    readJsonFile<Day3DemoSummary>(path.join(ARTIFACTS_DIR, "day3f-demo-summary.json")),
  ]);

  const gptBaseline = buildGptSource(gptSummary, catalog, day3Summary);
  const fakeBaseline = await buildFakeSource(fakeSummary, catalog, day3Summary);

  const newRegressions = day3Summary.verification_results.reviewed_outcomes.reduce(
    (count, outcome) => count + outcome.regressions.length,
    0,
  );

  return {
    title: "Memory MRI",
    description:
      "Audit how memory retrieval changes agent decisions across benchmarked customer support, DevOps, and workplace expense scenarios.",
    gptBaseline,
    fakeBaseline,
    domainCards: buildDomainCards(gptBaseline, day3Summary),
    failureCards: buildFailureCards(gptBaseline, day3Summary, demoSummary),
    counts: {
      investigations: day3Summary.investigations.length,
      proposals: day3Summary.proposals.length,
      verificationArtifacts: day3Summary.artifact_ids.length,
      newRegressions,
    },
    recentInvestigations: buildRecentInvestigations(day3Summary),
    recentActivity: buildRecentActivity(day3Summary),
    frozenSnapshotTimestamp: day3Summary.generated_at,
  };
}

export async function loadBenchmarkExplorerEvidence(): Promise<BenchmarkExplorerEvidence> {
  const dashboard = await loadDashboardEvidence();
  return {
    sources: {
      gpt: dashboard.gptBaseline,
      fake: dashboard.fakeBaseline,
    },
  };
}
