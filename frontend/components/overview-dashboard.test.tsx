import { render, screen } from "@testing-library/react";

import { OverviewDashboard } from "@/components/overview-dashboard";
import type { DashboardEvidence } from "@/lib/benchmark-shared";

const dashboardData: DashboardEvidence = {
  title: "Memory MRI",
  description: "Audit memory-driven decisions across benchmarked domains.",
  gptBaseline: {
    key: "gpt",
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
    categoryResults: {},
    scenarioRows: [
      {
        scenarioId: "cs_01",
        domain: "customer_support",
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
        scenarioId: "exp_09",
        domain: "workplace_expense",
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
    ],
    totalLatencyMs: 106070,
    tokenUsage: { inputTokens: 30336, outputTokens: 2993, totalTokens: 33329, billableApiCalls: 30 },
  },
  fakeBaseline: {
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
    domainResults: {
      customer_support: { attempted: 10, evaluated: 10, passed: 7, failed: 3, infrastructureErrors: 0 },
      devops: { attempted: 10, evaluated: 10, passed: 8, failed: 2, infrastructureErrors: 0 },
      workplace_expense: { attempted: 10, evaluated: 10, passed: 7, failed: 3, infrastructureErrors: 0 },
    },
    categoryResults: {},
    scenarioRows: [],
    totalLatencyMs: null,
    tokenUsage: null,
  },
  domainCards: [
    {
      domain: "customer_support",
      label: "Customer Support",
      scenarioCount: 10,
      gptPassCount: 9,
      gptFailureCount: 1,
      investigationCount: 1,
      statusLabel: "1 frozen GPT failure",
    },
    {
      domain: "devops",
      label: "DevOps Deployment",
      scenarioCount: 10,
      gptPassCount: 10,
      gptFailureCount: 0,
      investigationCount: 0,
      statusLabel: "all passing in frozen GPT run",
    },
    {
      domain: "workplace_expense",
      label: "Workplace Expense",
      scenarioCount: 10,
      gptPassCount: 9,
      gptFailureCount: 1,
      investigationCount: 1,
      statusLabel: "1 frozen GPT failure",
    },
  ],
  failureCards: [
    {
      scenarioId: "cs_01",
      domain: "customer_support",
      actualAction: "ASK_FOR_INFORMATION",
      expectedAction: "ISSUE_REFUND",
      investigationId: "inv_cs_01",
      investigationStatus: "investigated",
      replaySummary: "Removing a memory changed the action distribution but did not establish a support-valid repair.",
      verificationVerdict: "VERIFICATION_INCONCLUSIVE",
      artifactId: "artifact_cs_01",
      memoryDependenceClassification: "individual-memory dependent",
    },
    {
      scenarioId: "exp_09",
      domain: "workplace_expense",
      actualAction: "REQUEST_DOCUMENTATION",
      expectedAction: "DENY_EXPENSE",
      investigationId: "inv_exp_09",
      investigationStatus: "investigated",
      replaySummary: "Replay evidence did not justify a memory edit and the issue appears memory-independent.",
      verificationVerdict: "MEMORY_REPAIR_NOT_APPLICABLE",
      artifactId: "artifact_exp_09",
      memoryDependenceClassification: "likely memory-independent",
    },
  ],
  counts: {
    investigations: 2,
    proposals: 2,
    verificationArtifacts: 2,
    newRegressions: 0,
  },
  recentInvestigations: [
    {
      scenarioId: "cs_01",
      domain: "customer_support",
      investigationId: "inv_cs_01",
      evidenceSummary: "individual-memory dependent",
      latestProposal: "REQUIRE_HUMAN_CONFIRMATION",
      verdict: "VERIFICATION_INCONCLUSIVE",
    },
    {
      scenarioId: "exp_09",
      domain: "workplace_expense",
      investigationId: "inv_exp_09",
      evidenceSummary: "likely memory-independent",
      latestProposal: "ESCALATE_PROMPT_OR_POLICY_REVIEW",
      verdict: "MEMORY_REPAIR_NOT_APPLICABLE",
    },
  ],
  recentActivity: [
    {
      id: "inv_cs_01",
      type: "investigation",
      label: "cs_01 investigation",
      detail: "individual-memory dependent",
    },
  ],
  frozenSnapshotTimestamp: "2026-07-19T03:15:00Z",
};

describe("OverviewDashboard", () => {
  it("shows separated GPT and fake baseline metrics", () => {
    render(<OverviewDashboard data={dashboardData} />);

    expect(screen.getByText("Official GPT baseline")).toBeInTheDocument();
    expect(screen.getByText("Deterministic test baseline")).toBeInTheDocument();
    expect(screen.getByText("28/30")).toBeInTheDocument();
    expect(screen.getByText("22/30")).toBeInTheDocument();
    expect(screen.getByText(/repeatable regression runner/i)).toBeInTheDocument();
  });

  it("shows both frozen failure cards with expected actions in evaluation context", () => {
    render(<OverviewDashboard data={dashboardData} />);

    expect(screen.getAllByText("cs_01").length).toBeGreaterThan(0);
    expect(screen.getAllByText("exp_09").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Expected action:/i).length).toBe(2);
    expect(screen.getByText("ISSUE_REFUND")).toBeInTheDocument();
    expect(screen.getByText("DENY_EXPENSE")).toBeInTheDocument();
  });
});
