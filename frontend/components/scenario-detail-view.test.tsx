import { render, screen } from "@testing-library/react";

import { ScenarioDetailView } from "@/components/scenario-detail-view";
import type { ScenarioDetailEvidence } from "@/lib/benchmark-shared";

const baseData: ScenarioDetailEvidence = {
  scenarioId: "cs_01",
  title: "Refund blocked by stale old no-refund note",
  domain: "customer_support",
  benchmarkMode: true,
  selectedSource: "gpt",
  selectedRunnerLabel: "GPT-5.6",
  investigationStatus: "investigated",
  verificationVerdict: "VERIFICATION_INCONCLUSIVE",
  latestTraceTimestamp: "2026-07-18T05:42:23.462472Z",
  benchmarkEvaluation: {
    benchmarkVersion: "gpt-baseline-summary.json",
    runnerType: "OpenAIAgentRunner",
    expectedAction: "ISSUE_REFUND",
    actualAction: "ASK_FOR_INFORMATION",
    passed: false,
    failureCategory: "stale-memory",
    infrastructureError: null,
    evaluatorName: "deterministic benchmark evaluator",
  },
  deterministicComparison: {
    runnerType: "FakeAgentRunner",
    expectedAction: "ISSUE_REFUND",
    actualAction: "ISSUE_REFUND",
    passed: true,
    benchmarkVersion: "day1-mixed-baseline-summary.json",
  },
  selectedTrace: {
    traceId: "trace_cs_01_official",
    scenarioId: "cs_01",
    runId: "run_cs_01",
    domain: "customer_support",
    userInput: "Customer says they were double charged and wants a refund.",
    runnerLabel: "GPT-5.6",
    requestedModel: "gpt-5.6",
    responseModel: "gpt-5.6-sol",
    model: "gpt-5.6-sol",
    promptVersion: "v1",
    promptContentHash: "prompt-hash-1",
    agentInputSchemaVersion: "day2a-v1",
    requestHash: "request-hash-1",
    retrievedMemoryIds: ["cs_01_mem_1", "cs_01_mem_2", "cs_01_mem_3"],
    memories: [
      {
        memoryId: "cs_01_mem_1",
        entityId: "customer_123",
        content: "Current refund policy allows immediate refund for duplicate charge.",
        source: "policy",
        createdAt: "2026-07-01T00:00:00.000Z",
        validFrom: "2026-07-01T00:00:00.000Z",
        validUntil: null,
        status: "active",
        confidence: 0.98,
        retrievalPriority: 100,
        supersedes: ["cs_01_mem_2"],
        tags: ["policy", "current"],
        operationalMetadata: { region: "us" },
        analysisFlags: [],
      },
      {
        memoryId: "cs_01_mem_2",
        entityId: "customer_123",
        content: "Old refund guidance said duplicate charges required more review.",
        source: "policy",
        createdAt: "2025-10-01T00:00:00.000Z",
        validFrom: "2025-10-01T00:00:00.000Z",
        validUntil: "2026-06-30T00:00:00.000Z",
        status: "stale",
        confidence: 0.77,
        retrievalPriority: 80,
        supersedes: [],
        tags: ["policy", "stale"],
        operationalMetadata: { region: "us" },
        analysisFlags: ["wrong context analysis"],
      },
      {
        memoryId: "cs_01_mem_3",
        entityId: "customer_123",
        content: "Account is in good standing.",
        source: "crm",
        createdAt: "2026-07-10T00:00:00.000Z",
        validFrom: "2026-07-10T00:00:00.000Z",
        validUntil: null,
        status: "uncertain",
        confidence: 0.61,
        retrievalPriority: 50,
        supersedes: [],
        tags: ["customer-status"],
        operationalMetadata: { standing: "good" },
        analysisFlags: [],
      },
    ],
    selectedAction: "ASK_FOR_INFORMATION",
    actionArguments: { fields: ["order_id"] },
    citedMemoryIds: ["cs_01_mem_2"],
    conciseRationale: "An older policy note suggests more documentation may be required.",
    uncertainty: 0.41,
    needsHumanReview: true,
    passed: false,
    executionSource: "live",
    cacheLookupLatencyMs: 4,
    originalModelLatencyMs: 1832,
    latencyMs: 1832,
    tokenUsage: { input_tokens: 900, output_tokens: 120, total_tokens: 1020 },
    requestTokenUsage: { input_tokens: 900, output_tokens: 120, total_tokens: 1020 },
    cachedOriginalTokenUsage: null,
    billableApiCall: true,
    cacheEnabled: true,
    cacheHit: false,
    cachePath: "artifacts/openai_cache/request-hash-1.json",
    error: null,
    createdAt: "2026-07-18T05:42:23.462472Z",
    toolCallResponseId: "resp_123",
    toolCallCacheHit: false,
    gitCommitHash: "3464c56",
    timeline: [
      {
        id: "user-request",
        label: "User request received",
        status: "complete",
        detail: "Customer says they were double charged and wants a refund.",
        timestamp: "2026-07-18T05:42:23.462472Z",
        evidenceType: "support",
        traceId: "trace_cs_01_official",
      },
      {
        id: "action-selected",
        label: "Runner selected action",
        status: "warning",
        detail: "ASK_FOR_INFORMATION because older policy evidence was weighted too highly.",
        timestamp: null,
        evidenceType: "semantic",
        traceId: "trace_cs_01_official",
      },
      {
        id: "evaluator-result",
        label: "Deterministic evaluator result",
        status: "warning",
        detail: "Selected action differed from the expected benchmark action.",
        timestamp: null,
        evidenceType: "support",
        traceId: "trace_cs_01_official",
      },
    ],
    kind: "official-gpt-baseline",
    kindLabel: "official frozen GPT baseline",
    sourceLabel: "artifacts/gpt-baseline-traces/cs_01.json",
    officialBaseline: true,
  },
  traces: [
    {
      traceId: "trace_cs_01_official",
      scenarioId: "cs_01",
      runId: "run_cs_01",
      domain: "customer_support",
      userInput: "Customer says they were double charged and wants a refund.",
      runnerLabel: "GPT-5.6",
      requestedModel: "gpt-5.6",
      responseModel: "gpt-5.6-sol",
      model: "gpt-5.6-sol",
      promptVersion: "v1",
      promptContentHash: "prompt-hash-1",
      agentInputSchemaVersion: "day2a-v1",
      requestHash: "request-hash-1",
      retrievedMemoryIds: ["cs_01_mem_1", "cs_01_mem_2", "cs_01_mem_3"],
      memories: [],
      selectedAction: "ASK_FOR_INFORMATION",
      actionArguments: { fields: ["order_id"] },
      citedMemoryIds: ["cs_01_mem_2"],
      conciseRationale: "An older policy note suggests more documentation may be required.",
      uncertainty: 0.41,
      needsHumanReview: true,
      passed: false,
      executionSource: "live",
      cacheLookupLatencyMs: 4,
      originalModelLatencyMs: 1832,
      latencyMs: 1832,
      tokenUsage: { input_tokens: 900, output_tokens: 120, total_tokens: 1020 },
      requestTokenUsage: { input_tokens: 900, output_tokens: 120, total_tokens: 1020 },
      cachedOriginalTokenUsage: null,
      billableApiCall: true,
      cacheEnabled: true,
      cacheHit: false,
      cachePath: "artifacts/openai_cache/request-hash-1.json",
      error: null,
      createdAt: "2026-07-18T05:42:23.462472Z",
      toolCallResponseId: "resp_123",
      toolCallCacheHit: false,
      gitCommitHash: "3464c56",
      timeline: [],
      kind: "official-gpt-baseline",
      kindLabel: "official frozen GPT baseline",
      sourceLabel: "artifacts/gpt-baseline-traces/cs_01.json",
      officialBaseline: true,
    },
    {
      traceId: "trace_cs_01_replay",
      scenarioId: "cs_01",
      runId: "run_cs_01_replay",
      domain: "customer_support",
      userInput: "Customer says they were double charged and wants a refund.",
      runnerLabel: "FakeAgentRunner",
      requestedModel: "fake-deterministic",
      responseModel: "fake-deterministic",
      model: "fake-deterministic",
      promptVersion: "n/a",
      promptContentHash: null,
      agentInputSchemaVersion: "day2a-v1",
      requestHash: "request-hash-2",
      retrievedMemoryIds: ["cs_01_mem_1"],
      memories: [],
      selectedAction: "ISSUE_REFUND",
      actionArguments: {},
      citedMemoryIds: ["cs_01_mem_1"],
      conciseRationale: "Current policy is sufficient.",
      uncertainty: 0.08,
      needsHumanReview: false,
      passed: true,
      executionSource: "replay",
      cacheLookupLatencyMs: null,
      originalModelLatencyMs: null,
      latencyMs: 3,
      tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
      requestTokenUsage: null,
      cachedOriginalTokenUsage: null,
      billableApiCall: false,
      cacheEnabled: false,
      cacheHit: false,
      cachePath: null,
      error: null,
      createdAt: "2026-07-18T06:00:00.000Z",
      toolCallResponseId: null,
      toolCallCacheHit: null,
      gitCommitHash: null,
      timeline: [],
      kind: "investigation-replay",
      kindLabel: "investigation replay trace",
      sourceLabel: "artifacts/investigations/inv_cs_01/traces/replay.json",
      officialBaseline: false,
    },
  ],
  traceNotice: null,
  evidenceLinks: [
    { label: "Investigation", href: "/investigations?id=inv_cs_01", status: "available" },
    { label: "Individual replay", href: "/investigations?id=inv_cs_01#individual-replay", status: "available" },
    { label: "Suspicion analysis", href: null, status: "missing" },
    { label: "Contradictions", href: "/investigations?id=inv_cs_01#contradictions", status: "available" },
    { label: "Pairwise replay", href: null, status: "missing" },
    { label: "Repair proposal", href: "/investigations?id=inv_cs_01#proposal-1", status: "available" },
    { label: "Verification artifact", href: "/artifacts?id=artifact_cs_01", status: "available" },
    { label: "Verification record", href: null, status: "missing" },
    { label: "Back to benchmark explorer", href: "/benchmarks?source=gpt&query=cs_01", status: "available" },
  ],
};

describe("ScenarioDetailView", () => {
  it("renders the detail sections and observable structured output", () => {
    render(<ScenarioDetailView data={baseData} />);

    expect(screen.getByText("Scenario Header")).toBeInTheDocument();
    expect(screen.getByText("Agent Input")).toBeInTheDocument();
    expect(screen.getByText("Benchmark Evaluation Information")).toBeInTheDocument();
    expect(screen.getByText("Execution Timeline")).toBeInTheDocument();
    expect(screen.getByText("Memories Retrieved")).toBeInTheDocument();
    expect(screen.getByText("Agent Response")).toBeInTheDocument();
    expect(screen.getByText("Trace Metadata")).toBeInTheDocument();
    expect(screen.getAllByText("ASK_FOR_INFORMATION").length).toBeGreaterThan(0);
    expect(screen.getByText("An older policy note suggests more documentation may be required.")).toBeInTheDocument();
  });

  it("hides expected-action details outside benchmark evaluation mode", () => {
    render(<ScenarioDetailView data={baseData} showEvaluation={false} />);

    expect(screen.queryByText("Expected action")).not.toBeInTheDocument();
    expect(
      screen.getByText(/expected-action benchmark labels stay hidden on this view/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("ISSUE_REFUND")).not.toBeInTheDocument();
  });

  it("renders memory states and wrong-context analysis markers", () => {
    render(<ScenarioDetailView data={baseData} />);

    expect(screen.getByText("cs_01_mem_1")).toBeInTheDocument();
    expect(screen.getAllByText("cs_01_mem_2").length).toBeGreaterThan(0);
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getAllByText("stale").length).toBeGreaterThan(0);
    expect(screen.getByText("uncertain")).toBeInTheDocument();
    expect(screen.getByText("wrong context analysis")).toBeInTheDocument();
  });

  it("renders infrastructure errors separately from evaluated failures", () => {
    const erroredData: ScenarioDetailEvidence = {
      ...baseData,
      benchmarkEvaluation: {
        ...baseData.benchmarkEvaluation,
        infrastructureError: "OpenAI timeout after 2 retries.",
      },
      selectedTrace: {
        ...baseData.selectedTrace!,
        error: {
          code: "timeout",
          message: "OpenAI timeout after 2 retries.",
          retryable: true,
          attempts: 2,
        },
      },
    };

    render(<ScenarioDetailView data={erroredData} />);

    expect(screen.getAllByText("Infrastructure error").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/OpenAI timeout after 2 retries./i).length).toBeGreaterThan(0);
  });

  it("shows trace switching with GPT and fake labels", () => {
    render(<ScenarioDetailView data={baseData} />);

    expect(screen.getByRole("link", { name: /official frozen GPT baseline/i })).toHaveAttribute(
      "href",
      "/benchmarks/cs_01?source=gpt&trace=trace_cs_01_official",
    );
    expect(screen.getByRole("link", { name: /investigation replay trace/i })).toHaveAttribute(
      "href",
      "/benchmarks/cs_01?source=gpt&trace=trace_cs_01_replay",
    );
    expect(screen.getAllByText("GPT-5.6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("FakeAgentRunner").length).toBeGreaterThan(0);
  });

  it("renders disabled evidence navigation when evidence is missing", () => {
    render(<ScenarioDetailView data={baseData} />);

    expect(screen.getByText("Suspicion analysis unavailable")).toBeInTheDocument();
    expect(screen.getByText("Pairwise replay unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Verification artifact" })).toHaveAttribute(
      "href",
      "/artifacts?id=artifact_cs_01",
    );
  });

  it("shows cache metadata and billing state", () => {
    render(<ScenarioDetailView data={baseData} />);

    expect(screen.getByText("prompt-hash-1")).toBeInTheDocument();
    expect(screen.getByText("request-hash-1")).toBeInTheDocument();
    expect(screen.getByText("3464c56")).toBeInTheDocument();
    expect(screen.getByText("1832 ms")).toBeInTheDocument();
    expect(screen.getByText(/Cache lookup: 4 ms/i)).toBeInTheDocument();
    expect(screen.getByText("miss")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
  });
});
