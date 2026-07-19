import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MemoryInfluenceGraph } from "@/components/memory-influence-graph";
import type { MemoryInfluenceGraphEvidence } from "@/lib/benchmark-shared";

const graphData: MemoryInfluenceGraphEvidence = {
  scenarioId: "cs_01",
  domain: "customer_support",
  selectedTraceId: "trace_cs_01",
  originalAction: "ASK_FOR_INFORMATION",
  expectedAction: "ISSUE_REFUND",
  classification: "individual-memory dependent",
  noMemoryControlPreservedWrongAction: true,
  supportValiditySummary:
    "Removing cs_01_mem_2 changes the action, but the corrected outcome is not support-valid.",
  proposal: {
    proposalId: "proposal_cs_01",
    repairType: "REQUIRE_HUMAN_CONFIRMATION",
    status: "applied",
    conciseExplanation:
      "Replay removal changed behavior, but ISSUE_REFUND remains unsupported because the amount is missing.",
    targetMemoryIds: ["cs_01_mem_2"],
  },
  memories: [
    {
      memoryId: "cs_01_mem_1",
      shortContent: "Expired legacy duplicate-charge refund note.",
      content: "Expired legacy duplicate-charge refund note.",
      status: "stale",
      freshnessState: "stale",
      entityId: "customer_8821",
      retrievalPriority: 99,
      source: "legacy_policy_sync",
      createdAt: "2024-02-01T00:00:00Z",
      validFrom: "2024-02-01T00:00:00Z",
      validUntil: "2024-12-31T00:00:00Z",
      confidence: 0.81,
      supersedes: [],
      tags: ["legacy"],
      operationalMetadata: { memory_role: "legacy_policy" },
      observedRetrieval: true,
      observedCitation: false,
      suspicionRank: 1,
      suspiciousWithoutObservedInfluence: true,
      deterministicSuspicionReasons: [
        "Stale status in the operational memory snapshot.",
        "Very high retrieval priority may outweigh more relevant evidence.",
      ],
      semanticIssueTypes: ["stale", "superseded", "contradictory", "excessive_priority"],
      semanticHypotheses: [
        "Expired legacy policy is superseded by the current playbook but retains the highest retrieval priority.",
      ],
      semanticSuspicionReasons: [],
      strongestIndividualInfluence: 0,
      strongestInteractionInfluence: 1,
      individualReplayResults: [],
      pairwiseParticipation: [
        {
          memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
          interventionType: "REMOVE_MEMORIES",
          combinedInfluence: 1,
          interactionScore: 0,
          interactionSynergy: 0,
          combinedActionDistribution: { ISSUE_REFUND: 3 },
          supportValid: false,
          requiresHumanReview: true,
          supportExplanation: "Outcome changed but remained unsupported.",
          evidenceClassification: "dominated by one memory",
        },
      ],
      contradictionRelationships: [
        {
          memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
          deterministicRelationship: {
            relationship: "supersedes",
            conciseReason: "cs_01_mem_2 explicitly supersedes cs_01_mem_1 in metadata.",
            confidence: 1,
            relevantFields: ["supersedes", "status"],
          },
          semanticRelationship: {
            relationship: "supersedes",
            conciseExplanation:
              "The current playbook explicitly supersedes the outdated approval policy.",
            confidence: 0.99,
            requiresHumanReview: false,
          },
          relationshipsAgree: true,
          pairwiseReplayPerformed: false,
        },
      ],
      proposalTargeted: false,
      supportValidityAudit: ["Outcome changed but remained unsupported."],
    },
    {
      memoryId: "cs_01_mem_2",
      shortContent: "Current duplicate-charge refund policy.",
      content: "Current duplicate-charge refund policy.",
      status: "active",
      freshnessState: "active",
      entityId: "customer_8821",
      retrievalPriority: 80,
      source: "policy_portal",
      createdAt: "2026-01-15T00:00:00Z",
      validFrom: "2026-01-15T00:00:00Z",
      validUntil: null,
      confidence: 0.97,
      supersedes: ["cs_01_mem_1"],
      tags: ["current-policy"],
      operationalMetadata: { memory_role: "policy" },
      observedRetrieval: true,
      observedCitation: true,
      suspicionRank: 3,
      suspiciousWithoutObservedInfluence: false,
      deterministicSuspicionReasons: ["Supersedes cs_01_mem_1 in metadata."],
      semanticIssueTypes: [],
      semanticHypotheses: [],
      semanticSuspicionReasons: [],
      strongestIndividualInfluence: 1,
      strongestInteractionInfluence: 1,
      individualReplayResults: [
        {
          interventionType: "REMOVE_MEMORY",
          targetMemoryIds: ["cs_01_mem_2"],
          successfulRuns: 3,
          totalRuns: 3,
          successRate: 1,
          influenceDelta: 1,
          actionDistribution: { ISSUE_REFUND: 3 },
          supportValid: false,
          requiresHumanReview: true,
          supportExplanation: "Expected action appeared, but the amount was still missing.",
        },
      ],
      pairwiseParticipation: [
        {
          memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
          interventionType: "REMOVE_MEMORIES",
          combinedInfluence: 1,
          interactionScore: 0,
          interactionSynergy: 0,
          combinedActionDistribution: { ISSUE_REFUND: 3 },
          supportValid: false,
          requiresHumanReview: true,
          supportExplanation: "Outcome changed but remained unsupported.",
          evidenceClassification: "dominated by one memory",
        },
      ],
      contradictionRelationships: [],
      proposalTargeted: true,
      supportValidityAudit: [
        "Expected action appeared, but the amount was still missing.",
      ],
    },
    {
      memoryId: "cs_01_mem_3",
      shortContent: "Billing evidence confirms duplicate charges.",
      content: "Billing evidence confirms duplicate charges.",
      status: "active",
      freshnessState: "active",
      entityId: "order_8821",
      retrievalPriority: 70,
      source: "billing_ledger",
      createdAt: "2026-07-01T09:00:00Z",
      validFrom: "2026-07-01T09:00:00Z",
      validUntil: null,
      confidence: 0.99,
      supersedes: [],
      tags: ["evidence"],
      operationalMetadata: { memory_role: "evidence" },
      observedRetrieval: true,
      observedCitation: false,
      suspicionRank: 2,
      suspiciousWithoutObservedInfluence: false,
      deterministicSuspicionReasons: [],
      semanticIssueTypes: [],
      semanticHypotheses: [
        "Current ledger evidence supports two settled charges for the referenced order.",
      ],
      semanticSuspicionReasons: [],
      strongestIndividualInfluence: 0,
      strongestInteractionInfluence: 0,
      individualReplayResults: [],
      pairwiseParticipation: [],
      contradictionRelationships: [],
      proposalTargeted: false,
      supportValidityAudit: [],
    },
  ],
  pairwiseInteractions: [
    {
      memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
      interventionType: "REMOVE_MEMORIES",
      combinedInfluence: 1,
      interactionScore: 0,
      interactionSynergy: 0,
      combinedActionDistribution: { ISSUE_REFUND: 3 },
      supportValid: false,
      requiresHumanReview: true,
      supportExplanation: "Outcome changed but remained unsupported.",
      evidenceClassification: "dominated by one memory",
    },
  ],
  contradictions: [
    {
      memoryIds: ["cs_01_mem_1", "cs_01_mem_2"],
      deterministicRelationship: {
        relationship: "supersedes",
        conciseReason: "cs_01_mem_2 explicitly supersedes cs_01_mem_1 in metadata.",
        confidence: 1,
        relevantFields: ["supersedes", "status"],
      },
      semanticRelationship: {
        relationship: "supersedes",
        conciseExplanation:
          "The current playbook explicitly supersedes the outdated approval policy.",
        confidence: 0.99,
        requiresHumanReview: false,
      },
      relationshipsAgree: true,
      pairwiseReplayPerformed: false,
    },
  ],
};

describe("MemoryInfluenceGraph", () => {
  it("renders accessibility labels and the alternative evidence table", () => {
    render(<MemoryInfluenceGraph data={graphData} />);

    expect(
      screen.getByRole("img", { name: /memory influence graph for cs_01/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alternative evidence table")).toBeInTheDocument();
    expect(screen.getAllByText("Observed retrieval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Semantic hypothesis").length).toBeGreaterThan(0);
  });

  it("opens the memory detail panel with replay and contradiction evidence", async () => {
    const user = userEvent.setup();
    render(<MemoryInfluenceGraph data={graphData} />);

    await user.click(screen.getByRole("button", { name: /memory cs_01_mem_2/i }));

    expect(screen.getByText("Deterministic suspicion reasons")).toBeInTheDocument();
    expect(screen.getAllByText(/Supersedes cs_01_mem_1 in metadata./i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Expected action appeared, but the amount was still missing./i)).toBeInTheDocument();
    expect(screen.getByText(/proposal targeted/i)).toBeInTheDocument();
  });

  it("supports evidence filters and hiding unrelated memories", async () => {
    const user = userEvent.setup();
    render(<MemoryInfluenceGraph data={graphData} />);

    await user.click(screen.getByRole("checkbox", { name: /Semantic hypothesis/i }));
    expect(screen.queryByText("semantic: supersedes")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /Hide unrelated memories/i }));
    await user.click(screen.getByRole("button", { name: /memory cs_01_mem_2/i }));

    expect(screen.queryByRole("button", { name: /memory cs_01_mem_3/i })).not.toBeInTheDocument();
  });

  it("shows the cs_01 mismatch truthfully in the details panel", async () => {
    const user = userEvent.setup();
    render(<MemoryInfluenceGraph data={graphData} />);

    await user.click(screen.getByRole("button", { name: /memory cs_01_mem_1/i }));

    expect(screen.getByText(/rank #1/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Very high retrieval priority may outweigh more relevant evidence./i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Strongest pair: cs_01_mem_1 \+ cs_01_mem_2; supported false./i),
    ).toBeInTheDocument();
  });

  it("renders the exp_09 zero-effect state and memory-independent classification", () => {
    const exp09Data: MemoryInfluenceGraphEvidence = {
      ...graphData,
      scenarioId: "exp_09",
      domain: "workplace_expense",
      classification: "likely memory-independent",
      supportValiditySummary:
        "Replay evidence does not justify a memory edit. The failure appears memory-independent.",
      proposal: {
        proposalId: "proposal_exp_09",
        repairType: "ESCALATE_PROMPT_OR_POLICY_REVIEW",
        status: "proposed",
        conciseExplanation: "No memory repair recommended.",
        targetMemoryIds: [],
      },
      memories: graphData.memories.map((memory, index) => ({
        ...memory,
        memoryId: `exp_09_mem_${index + 1}`,
        strongestIndividualInfluence: 0,
        strongestInteractionInfluence: 0,
        suspiciousWithoutObservedInfluence: index === 0,
        semanticIssueTypes: index === 0 ? ["wrong_context", "excessive_priority"] : [],
      })),
      pairwiseInteractions: [
        {
          memoryIds: ["exp_09_mem_1", "exp_09_mem_2"],
          interventionType: "REMOVE_MEMORIES",
          combinedInfluence: 0,
          interactionScore: 0,
          interactionSynergy: 0,
          combinedActionDistribution: { REQUEST_DOCUMENTATION: 3 },
          supportValid: false,
          requiresHumanReview: false,
          supportExplanation: "Intervention did not reach the expected action.",
          evidenceClassification: "no observed pairwise influence",
        },
      ],
    };

    render(<MemoryInfluenceGraph data={exp09Data} />);

    expect(screen.getByText(/Classification: likely memory-independent/i)).toBeInTheDocument();
    expect(
      screen.getByText(/No-memory control preserved wrong action: true/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Replay evidence does not justify a memory edit./i)).toBeInTheDocument();
  });
});
