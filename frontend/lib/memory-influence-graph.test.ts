import type { MemoryInfluenceGraphEvidence } from "@/lib/benchmark-shared";
import {
  buildGraphModel,
  DEFAULT_GRAPH_FILTERS,
  filterGraphModel,
  getMemoryDisplayFlags,
} from "@/lib/memory-influence-graph";

const cs01Graph: MemoryInfluenceGraphEvidence = {
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
      operationalMetadata: {},
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
      operationalMetadata: {},
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
      operationalMetadata: {},
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

const exp09Graph: MemoryInfluenceGraphEvidence = {
  ...cs01Graph,
  scenarioId: "exp_09",
  domain: "workplace_expense",
  selectedTraceId: "trace_exp_09",
  originalAction: "REQUEST_DOCUMENTATION",
  expectedAction: "DENY_EXPENSE",
  classification: "likely memory-independent",
  noMemoryControlPreservedWrongAction: true,
  supportValiditySummary:
    "Replay evidence does not justify a memory edit. The failure appears memory-independent.",
  proposal: {
    proposalId: "proposal_exp_09",
    repairType: "ESCALATE_PROMPT_OR_POLICY_REVIEW",
    status: "proposed",
    conciseExplanation: "No memory repair recommended.",
    targetMemoryIds: [],
  },
  memories: cs01Graph.memories.map((memory, index) => ({
    ...memory,
    memoryId: `exp_09_mem_${index + 1}`,
    shortContent:
      index === 0
        ? "Relocation stipend note with wrong-context relevance."
        : index === 1
          ? "Meal policy requiring documented per-diem eligibility."
          : "Receipt showing employee-only dinner.",
    content:
      index === 0
        ? "Relocation stipend note with wrong-context relevance."
        : index === 1
          ? "Meal policy requiring documented per-diem eligibility."
          : "Receipt showing employee-only dinner.",
    freshnessState: "active",
    status: "active",
    observedCitation: index === 0,
    suspicionRank: index + 1,
    suspiciousWithoutObservedInfluence: index === 0,
    deterministicSuspicionReasons:
      index === 0
        ? ["Very high retrieval priority may outweigh more relevant evidence."]
        : [],
    semanticIssueTypes: index === 0 ? ["wrong_context", "excessive_priority"] : [],
    semanticHypotheses:
      index === 0
        ? [
            "Temporary relocation stipend eligibility does not establish per-diem eligibility for customer travel.",
          ]
        : [],
    strongestIndividualInfluence: 0,
    strongestInteractionInfluence: 0,
    individualReplayResults: memory.individualReplayResults.map((result) => ({
      ...result,
      targetMemoryIds: [`exp_09_mem_${index + 1}`],
      influenceDelta: 0,
      actionDistribution: { REQUEST_DOCUMENTATION: 3 },
    })),
    pairwiseParticipation: [],
    contradictionRelationships: [],
    proposalTargeted: false,
    supportValidityAudit: [],
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
  contradictions: [
    {
      memoryIds: ["exp_09_mem_1", "exp_09_mem_2"],
      deterministicRelationship: {
        relationship: "unrelated",
        conciseReason: "Metadata does not show a direct relationship between the memories.",
        confidence: 0.6,
        relevantFields: [],
      },
      semanticRelationship: {
        relationship: "unrelated",
        conciseExplanation:
          "Relocation stipend eligibility does not address customer-travel meal policy.",
        confidence: 0.95,
        requiresHumanReview: false,
      },
      relationshipsAgree: true,
      pairwiseReplayPerformed: false,
    },
  ],
};

describe("memory influence graph model", () => {
  it("generates the required node types", () => {
    const model = buildGraphModel(cs01Graph);

    expect(model.nodes.some((node) => node.type === "user-request")).toBe(true);
    expect(model.nodes.some((node) => node.type === "memory")).toBe(true);
    expect(model.nodes.some((node) => node.type === "agent-decision")).toBe(true);
    expect(model.nodes.some((node) => node.type === "tool-action")).toBe(true);
    expect(model.nodes.some((node) => node.type === "evaluator-outcome")).toBe(true);
    expect(model.nodes.some((node) => node.type === "repair-proposal")).toBe(true);
  });

  it("keeps semantic hypotheses separate from replay-supported evidence", () => {
    const model = buildGraphModel(cs01Graph);

    expect(model.edges.some((edge) => edge.type === "semantic-hypothesis")).toBe(true);
    expect(
      model.edges.some(
        (edge) => edge.type === "replay-supported" && edge.memoryIds.includes("cs_01_mem_2"),
      ),
    ).toBe(true);
    expect(
      model.edges.some(
        (edge) => edge.type === "replay-supported" && edge.memoryIds.includes("cs_01_mem_1"),
      ),
    ).toBe(false);
  });

  it("renders pairwise interaction edges with their own classification", () => {
    const model = buildGraphModel(cs01Graph);

    expect(
      model.edges.some(
        (edge) =>
          edge.type === "pairwise-interaction" &&
          edge.memoryIds.includes("cs_01_mem_1") &&
          edge.memoryIds.includes("cs_01_mem_2"),
      ),
    ).toBe(true);
  });

  it("can hide unrelated memories when a memory is selected", () => {
    const model = buildGraphModel(cs01Graph);
    const filtered = filterGraphModel(
      model,
      { ...DEFAULT_GRAPH_FILTERS, hideUnrelatedMemories: true },
      "cs_01_mem_2",
    );

    expect(filtered.nodes.some((node) => node.id === "memory:cs_01_mem_1")).toBe(true);
    expect(filtered.nodes.some((node) => node.id === "memory:cs_01_mem_2")).toBe(true);
    expect(filtered.nodes.some((node) => node.id === "memory:cs_01_mem_3")).toBe(false);
  });

  it("captures the cs_01 mismatch between suspicion and observed influence", () => {
    const [memory1, memory2] = cs01Graph.memories;

    expect(memory1.suspicionRank).toBe(1);
    expect(memory1.suspiciousWithoutObservedInfluence).toBe(true);
    expect(memory1.strongestIndividualInfluence).toBe(0);
    expect(memory2.strongestIndividualInfluence).toBe(1);
    expect(memory2.pairwiseParticipation[0]?.evidenceClassification).toBe("dominated by one memory");
  });

  it("captures the exp_09 zero-effect and memory-independent state", () => {
    expect(exp09Graph.classification).toBe("likely memory-independent");
    expect(exp09Graph.noMemoryControlPreservedWrongAction).toBe(true);
    expect(exp09Graph.memories.every((memory) => memory.strongestIndividualInfluence === 0)).toBe(
      true,
    );
    expect(exp09Graph.pairwiseInteractions.every((pair) => pair.combinedInfluence === 0)).toBe(
      true,
    );
  });

  it("marks deterministic, semantic, and replay flags separately", () => {
    expect(getMemoryDisplayFlags(cs01Graph.memories[0])).toEqual(["D", "S", "P"]);
    expect(getMemoryDisplayFlags(cs01Graph.memories[1])).toEqual(["D", "I", "P"]);
  });
});
