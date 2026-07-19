import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReplayLaboratory } from "@/components/replay-laboratory";
import type { ReplayLabEvidence } from "@/lib/benchmark-shared";

const refreshSpy = vi.fn();
const runIndividualReplaySpy = vi.fn();
const runPairwiseReplaySpy = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: refreshSpy,
  }),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      runIndividualReplay: (...args: unknown[]) => runIndividualReplaySpy(...args),
      runPairwiseReplay: (...args: unknown[]) => runPairwiseReplaySpy(...args),
    },
  };
});

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const baseData: ReplayLabEvidence = {
  investigationId: "inv_6d6c10d634c140f3af029a3eb7826bde",
  scenarioId: "cs_01",
  title: "Refund blocked by stale old no-refund note",
  domain: "customer_support",
  benchmarkMode: true,
  originalAction: "ASK_FOR_INFORMATION",
  expectedAction: "ISSUE_REFUND",
  runnerLabel: "GPT-5.6",
  requestedModel: "gpt-5.6",
  responseModel: "gpt-5.6-sol",
  promptVersion: "v1",
  promptContentHash: "prompt-hash-1",
  memoryDependenceClassification: "individual-memory dependent",
  cachePolicy: "cache disabled during replay to measure repeated live executions",
  runCount: 3,
  parentTraceId: "trace_cs_01",
  latestTimestamp: "2026-07-18T07:35:30.495058Z",
  proposalId: "proposal_cs_01",
  proposalSummary:
    "Replay removal changed behavior, but ISSUE_REFUND remains unsupported because the amount is missing.",
  proposalStatus: "applied",
  verificationVerdict: "VERIFICATION_INCONCLUSIVE",
  artifactId: "artifact_cs_01",
  supportValiditySummary:
    "Intervention REMOVE_MEMORY on cs_01_mem_2 changed the action distribution to {'ISSUE_REFUND': 3}, but support must be checked separately before treating it as a valid repair.",
  suspiciousMemoryIds: ["cs_01_mem_1"],
  contradictionPairs: ["cs_01_mem_1/cs_01_mem_2"],
  scenarioLinks: [
    { label: "Parent trace", href: "/benchmarks/cs_01?trace=trace_cs_01", status: "available" },
    { label: "Verification artifact", href: "/artifacts?id=artifact_cs_01", status: "available" },
  ],
  snapshot: [
    {
      memoryId: "cs_01_mem_1",
      entityId: "customer_8821",
      content: "Old 2024 pilot note said duplicate-charge refunds required manager approval.",
      source: "legacy_policy_sync",
      createdAt: "2024-02-01T00:00:00Z",
      validFrom: "2024-02-01T00:00:00Z",
      validUntil: "2024-12-31T00:00:00Z",
      status: "stale",
      confidence: 0.81,
      retrievalPriority: 99,
      supersedes: [],
      tags: ["legacy"],
      operationalMetadata: { memory_role: "legacy_policy" },
      analysisFlags: [],
    },
    {
      memoryId: "cs_01_mem_2",
      entityId: "customer_8821",
      content: "Current refund playbook allows direct refund for verified duplicate charges under $500.",
      source: "policy_portal",
      createdAt: "2026-01-15T00:00:00Z",
      validFrom: "2026-01-15T00:00:00Z",
      validUntil: null,
      status: "active",
      confidence: 0.97,
      retrievalPriority: 80,
      supersedes: ["cs_01_mem_1"],
      tags: ["current-policy"],
      operationalMetadata: { memory_role: "policy" },
      analysisFlags: [],
    },
    {
      memoryId: "cs_01_mem_3",
      entityId: "order_8821",
      content: "Billing ledger shows two settled charges within one minute for the same order.",
      source: "billing_ledger",
      createdAt: "2026-07-01T09:00:00Z",
      validFrom: "2026-07-01T09:00:00Z",
      validUntil: null,
      status: "active",
      confidence: 0.99,
      retrievalPriority: 70,
      supersedes: [],
      tags: ["evidence"],
      operationalMetadata: { memory_role: "evidence" },
      analysisFlags: [],
    },
  ],
  individualResults: [
    {
      memoryId: "cs_01_mem_2",
      interventionType: "REMOVE_MEMORY",
      runCount: 3,
      originalSuccessfulRuns: 0,
      originalTotalRuns: 3,
      originalSuccessRate: 0,
      interventionSuccessfulRuns: 3,
      interventionTotalRuns: 3,
      interventionSuccessRate: 1,
      influenceDelta: 1,
      wilsonLow: 0.44,
      wilsonHigh: 1,
      originalActionDistribution: { ASK_FOR_INFORMATION: 3 },
      interventionActionDistribution: { ISSUE_REFUND: 3 },
      originalReplayStability: 1,
      interventionReplayStability: 1,
      originalErrors: [],
      interventionErrors: [],
      supportValid: false,
      requiresHumanReview: true,
      supportExplanation: "Expected action appeared, but the amount was still missing.",
      tokenUsage: null,
      traceLinks: [{ label: "Original trace 1", href: "/benchmarks/cs_01?trace=trace_a", status: "available" }],
      artifactLinks: [{ label: "individual-replay.json", href: "file:///tmp/individual-replay.json", status: "available" }],
    },
    {
      memoryId: "cs_01_mem_2",
      interventionType: "DISABLE_MEMORY",
      runCount: 3,
      originalSuccessfulRuns: 0,
      originalTotalRuns: 3,
      originalSuccessRate: 0,
      interventionSuccessfulRuns: 0,
      interventionTotalRuns: 3,
      interventionSuccessRate: 0,
      influenceDelta: 0,
      wilsonLow: 0,
      wilsonHigh: 0.56,
      originalActionDistribution: { ASK_FOR_INFORMATION: 3 },
      interventionActionDistribution: { REQUEST_MANAGER_APPROVAL: 3 },
      originalReplayStability: 1,
      interventionReplayStability: 1,
      originalErrors: [],
      interventionErrors: [],
      supportValid: false,
      requiresHumanReview: false,
      supportExplanation: "The intervention did not reach the expected action.",
      tokenUsage: null,
      traceLinks: [],
      artifactLinks: [],
    },
  ],
  pairwiseResults: [
    {
      memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
      interventionType: "REMOVE_MEMORIES",
      influenceA: 0,
      influenceB: 1,
      combinedInfluence: 1,
      interactionScore: 0,
      interactionSynergy: 0,
      combinedActionDistribution: { ISSUE_REFUND: 3 },
      runCount: 3,
      supportValid: false,
      requiresHumanReview: true,
      supportExplanation: "The intervention changed behavior, but the remaining snapshot no longer contains enough active policy and evidence to support the expected action confidently.",
      evidenceClassification: "dominated by one memory",
      infrastructureErrorCount: 0,
      tokenUsage: null,
      traceLinks: [],
      artifactLinks: [],
    },
  ],
  noMemoryControl: {
    controlType: "no-memory",
    targetMemoryId: null,
    runCount: 3,
    originalSuccessRate: 0,
    controlSuccessRate: 0,
    originalActionDistribution: { ASK_FOR_INFORMATION: 3 },
    controlActionDistribution: { ASK_FOR_INFORMATION: 3 },
    replayStability: 1,
    supportValid: false,
    requiresHumanReview: true,
    supportExplanation: "The intervention removed all memories, so the resulting decision is unsupported by memory evidence.",
    infrastructureErrorCount: 0,
    tokenUsage: null,
    traceLinks: [],
  },
  isolationControls: [
    {
      controlType: "isolate-memory",
      targetMemoryId: "cs_01_mem_3",
      runCount: 3,
      originalSuccessRate: 0,
      controlSuccessRate: 1,
      originalActionDistribution: { ASK_FOR_INFORMATION: 3 },
      controlActionDistribution: { ISSUE_REFUND: 3 },
      replayStability: 1,
      supportValid: false,
      requiresHumanReview: true,
      supportExplanation: "The intervention changed behavior, but the remaining snapshot no longer contains enough active policy and evidence to support the expected action confidently.",
      infrastructureErrorCount: 0,
      tokenUsage: null,
      traceLinks: [],
    },
  ],
  highlightedFindings: [
    "cs_01_mem_2 shows individual influence 1.0 under REMOVE_MEMORY, but the expected action is not support-valid.",
    "cs_01_mem_1 ranks highly suspicious while showing no individual replay effect.",
    "No-memory control preserved ASK_FOR_INFORMATION, so the failure does not disappear when all memory is removed.",
    "Isolating cs_01_mem_3 produced ISSUE_REFUND.",
  ],
};

describe("ReplayLaboratory", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    refreshSpy.mockReset();
    runIndividualReplaySpy.mockReset();
    runPairwiseReplaySpy.mockReset();
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "true",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "false",
    };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("renders preserved individual, pairwise, and control evidence", () => {
    renderWithProviders(<ReplayLaboratory data={baseData} />);

    expect(screen.getByText("Replay Laboratory")).toBeInTheDocument();
    expect(screen.getByText("Individual Replay")).toBeInTheDocument();
    expect(screen.getByText("Pairwise Replay")).toBeInTheDocument();
    expect(screen.getByText("Control Experiments")).toBeInTheDocument();
    expect(screen.getAllByText(/ASK_FOR_INFORMATION: 3/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ISSUE_REFUND: 3/i).length).toBeGreaterThan(0);
    expect(screen.getByText("0.44 to 1.00")).toBeInTheDocument();
  });

  it("shows support-validity warnings and null-effect preserved evidence", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReplayLaboratory data={baseData} />);

    await user.selectOptions(screen.getAllByLabelText(/Memory/i)[0], "cs_01_mem_2");
    await user.selectOptions(screen.getByLabelText(/Operation/i), "DISABLE_MEMORY");

    expect(screen.getByText(/The intervention did not reach the expected action./i)).toBeInTheDocument();
    expect(screen.getAllByText("0.00").length).toBeGreaterThan(0);
  });

  it("shows live-run confirmation safety when enabled", async () => {
    const user = userEvent.setup();
    process.env = {
      ...process.env,
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "true",
    };
    runIndividualReplaySpy.mockResolvedValue({});

    renderWithProviders(<ReplayLaboratory data={baseData} />);

    await user.click(screen.getByRole("button", { name: /Run selected individual replay/i }));

    expect(screen.getByText(/Confirmation required before launching a GPT-backed replay./i)).toBeInTheDocument();
    expect(screen.getAllByText(/repeated model runs may incur cost/i).length).toBeGreaterThan(0);
  });

  it("shows disabled-live-run messaging without launching a replay", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReplayLaboratory data={baseData} />);

    await user.click(screen.getByRole("button", { name: /Run selected individual replay/i }));

    expect(screen.getByText(/Live replay is disabled/i)).toBeInTheDocument();
    expect(runIndividualReplaySpy).not.toHaveBeenCalled();
  });

  it("renders the exp_09 memory-independent control conclusion truthfully", () => {
    renderWithProviders(
      <ReplayLaboratory
        data={{
          ...baseData,
          investigationId: "inv_exp_09",
          scenarioId: "exp_09",
          domain: "workplace_expense",
          originalAction: "REQUEST_DOCUMENTATION",
          expectedAction: "DENY_EXPENSE",
          memoryDependenceClassification: "likely memory-independent",
          highlightedFindings: [
            "All individual influence values remain 0.0 across preserved replay evidence.",
            "All pairwise combined influence values remain 0.0.",
          ],
          noMemoryControl: {
            ...baseData.noMemoryControl!,
            controlActionDistribution: { REQUEST_DOCUMENTATION: 3 },
          },
        }}
      />,
    );

    expect(
      screen.getByText(
        /Incorrect behavior persisted with no memories, indicating that prompt or policy interpretation is a stronger hypothesis than memory influence./i,
      ),
    ).toBeInTheDocument();
  });
});
