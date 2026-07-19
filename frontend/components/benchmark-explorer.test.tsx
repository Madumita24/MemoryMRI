import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BenchmarkExplorer } from "@/components/benchmark-explorer";
import type { BenchmarkExplorerEvidence } from "@/lib/benchmark-shared";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  confirm: vi.fn(),
  runBenchmark: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/benchmarks",
  useRouter: () => ({
    replace: mocks.replace,
  }),
  useSearchParams: () => new URLSearchParams("source=gpt"),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      runBenchmark: mocks.runBenchmark,
    },
  };
});

const rows = [
  {
    scenarioId: "cs_01",
    domain: "customer_support" as const,
    title: "Refund blocked by stale old no-refund note",
    memoryCount: 3,
    runnerLabel: "GPT-5.6",
    actualAction: "ASK_FOR_INFORMATION",
    expectedAction: "ISSUE_REFUND",
    passed: false,
    failureCategory: "stale-memory",
    traceId: "trace_cs_01",
    investigationId: "inv_cs_01",
    investigationStatus: "investigated",
    verificationVerdict: "VERIFICATION_INCONCLUSIVE",
    artifactId: "artifact_cs_01",
  },
  {
    scenarioId: "cs_02",
    domain: "customer_support" as const,
    title: "Contradictory refund thresholds",
    memoryCount: 3,
    runnerLabel: "GPT-5.6",
    actualAction: "REQUEST_MANAGER_APPROVAL",
    expectedAction: "REQUEST_MANAGER_APPROVAL",
    passed: true,
    failureCategory: "contradictory-memories",
    traceId: "trace_cs_02",
    investigationId: null,
    investigationStatus: "not investigated",
    verificationVerdict: null,
    artifactId: null,
  },
  {
    scenarioId: "dev_01",
    domain: "devops" as const,
    title: "Safe deploy with fresh production approval",
    memoryCount: 3,
    runnerLabel: "GPT-5.6",
    actualAction: "DEPLOY_PRODUCTION",
    expectedAction: "DEPLOY_PRODUCTION",
    passed: true,
    failureCategory: "stale-memory",
    traceId: "trace_dev_01",
    investigationId: null,
    investigationStatus: "not investigated",
    verificationVerdict: null,
    artifactId: null,
  },
  {
    scenarioId: "exp_09",
    domain: "workplace_expense" as const,
    title: "Wrong-context meal policy",
    memoryCount: 3,
    runnerLabel: "GPT-5.6",
    actualAction: "REQUEST_DOCUMENTATION",
    expectedAction: "DENY_EXPENSE",
    passed: false,
    failureCategory: "wrong-context-valid-memory",
    traceId: "trace_exp_09",
    investigationId: "inv_exp_09",
    investigationStatus: "investigated",
    verificationVerdict: "MEMORY_REPAIR_NOT_APPLICABLE",
    artifactId: "artifact_exp_09",
  },
];

const gptSource = {
  key: "gpt" as const,
  label: "Official GPT baseline",
  runnerType: "OpenAIAgentRunner",
  model: "gpt-5.6",
  promptVersion: "customer_support:v1 | devops:v1 | workplace_expense:v1",
  artifactSource: "artifacts/gpt-baseline-summary.json",
  benchmarkId: "artifacts/gpt-baseline-summary.json",
  timestamp: "2026-07-18T05:42:23.462472Z",
  overall: {
    attempted: 30,
    evaluated: 30,
    passed: 28,
    failed: 2,
    infrastructureErrors: 0,
    passRate: 28 / 30,
  },
  domainResults: {
    customer_support: { attempted: 10, evaluated: 10, passed: 9, failed: 1, infrastructureErrors: 0 },
    devops: { attempted: 10, evaluated: 10, passed: 10, failed: 0, infrastructureErrors: 0 },
    workplace_expense: { attempted: 10, evaluated: 10, passed: 9, failed: 1, infrastructureErrors: 0 },
  },
  categoryResults: {
    "stale-memory": { attempted: 3, evaluated: 3, passed: 2, failed: 1, infrastructureErrors: 0 },
  },
  scenarioRows: rows,
  totalLatencyMs: 106070,
  tokenUsage: { inputTokens: 30336, outputTokens: 2993, totalTokens: 33329, billableApiCalls: 30 },
};

const fakeRows = rows.map((row) => ({
  ...row,
  runnerLabel: "FakeAgentRunner",
  actualAction: row.scenarioId === "cs_01" ? "ISSUE_REFUND" : row.actualAction,
  failureCategory: null,
}));

const explorerData: BenchmarkExplorerEvidence = {
  sources: {
    gpt: gptSource,
    fake: {
      ...gptSource,
      key: "fake",
      label: "Deterministic fake baseline",
      runnerType: "FakeAgentRunner",
      model: null,
      promptVersion: "n/a (deterministic heuristics)",
      artifactSource: "artifacts/day1-mixed-baseline-summary.json",
      benchmarkId: "artifacts/day1-mixed-baseline-summary.json",
      timestamp: "2026-07-18T00:00:00.000Z",
      overall: {
        attempted: 30,
        evaluated: 30,
        passed: 22,
        failed: 8,
        infrastructureErrors: 0,
        passRate: 22 / 30,
      },
      scenarioRows: fakeRows,
      totalLatencyMs: null,
      tokenUsage: null,
    },
  },
};

describe("BenchmarkExplorer", () => {
  const originalEnv = process.env;
  const originalConfirm = window.confirm;

  beforeAll(() => {
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "false",
    };
    window.confirm = mocks.confirm;
  });

  beforeEach(() => {
    mocks.replace.mockReset();
    mocks.confirm.mockReset();
    mocks.runBenchmark.mockReset();
  });

  afterAll(() => {
    process.env = originalEnv;
    window.confirm = originalConfirm;
  });

  it("keeps GPT and fake metrics separated", () => {
    render(<BenchmarkExplorer data={explorerData} />);

    expect(
      screen.getByRole("button", { name: "Official GPT baseline" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/alternate source: Deterministic fake baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/this page never mixes GPT and FakeAgentRunner results/i)).toBeInTheDocument();
  });

  it("shows scenario rows without expected actions until evaluation details are enabled", async () => {
    const user = userEvent.setup();
    render(<BenchmarkExplorer data={explorerData} />);

    expect(screen.getByText("Refund blocked by stale old no-refund note")).toBeInTheDocument();
    expect(screen.queryByText("ISSUE_REFUND")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /show evaluation details/i }));

    expect(screen.getAllByText("ISSUE_REFUND").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/stale memory/i).length).toBeGreaterThan(0);
  });

  it("filters by domain, result, and text search", async () => {
    const user = userEvent.setup();
    render(<BenchmarkExplorer data={explorerData} />);

    await user.selectOptions(screen.getByLabelText("Domain"), "workplace_expense");
    expect(screen.getByText("exp_09")).toBeInTheDocument();
    expect(screen.queryByText("cs_01")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Result"), "failed");
    expect(screen.getByText("exp_09")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Search"));
    await user.type(screen.getByLabelText("Search"), "documentation");
    expect(screen.getByText("exp_09")).toBeInTheDocument();
  });

  it("shows empty state when filters remove every row", async () => {
    const user = userEvent.setup();
    render(<BenchmarkExplorer data={explorerData} />);

    await user.type(screen.getByLabelText("Search"), "missing-scenario");

    expect(screen.getByText(/No scenarios match the current filters/i)).toBeInTheDocument();
  });

  it("persists source selection in the URL", async () => {
    const user = userEvent.setup();
    render(<BenchmarkExplorer data={explorerData} />);

    await user.click(screen.getByRole("button", { name: /Deterministic fake baseline/i }));

    expect(mocks.replace).toHaveBeenCalledWith("/benchmarks?source=fake");
  });

  it("shows the live-run confirmation path when enabled", async () => {
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "true",
    };
    mocks.confirm.mockReturnValue(true);
    mocks.runBenchmark.mockResolvedValue({ run_id: "run_1", summary: { total_scenarios: 30, passed_scenarios: 28 } });

    const user = userEvent.setup();
    render(<BenchmarkExplorer data={explorerData} />);

    await user.click(screen.getByRole("button", { name: /run benchmark/i }));

    expect(mocks.confirm).toHaveBeenCalledTimes(1);
    expect(mocks.runBenchmark).toHaveBeenCalledWith({ runner: "openai" });
    expect(await screen.findByText(/Completed gpt benchmark run: 28\/30./i)).toBeInTheDocument();
  });
});
