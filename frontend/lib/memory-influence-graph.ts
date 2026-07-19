import type {
  MemoryInfluenceGraphEvidence,
  MemoryInfluenceMemoryEvidence,
  MemoryInfluencePairwiseInteraction,
} from "@/lib/benchmark-shared";

export type GraphEdgeType =
  | "observed-retrieval"
  | "agent-citation"
  | "metadata-relationship"
  | "semantic-hypothesis"
  | "replay-supported"
  | "pairwise-interaction"
  | "benchmark-evaluation"
  | "proposal-target";

export type GraphNodeType =
  | "user-request"
  | "memory"
  | "agent-decision"
  | "tool-action"
  | "evaluator-outcome"
  | "repair-proposal";

export type GraphNode = {
  id: string;
  type: GraphNodeType;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  ariaLabel: string;
  memoryId?: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: GraphEdgeType;
  label: string;
  detail: string;
  memoryIds: string[];
};

export type GraphFilters = Record<GraphEdgeType, boolean> & {
  hideUnrelatedMemories: boolean;
};

export type GraphModel = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export const DEFAULT_GRAPH_FILTERS: GraphFilters = {
  "observed-retrieval": true,
  "agent-citation": true,
  "metadata-relationship": true,
  "semantic-hypothesis": true,
  "replay-supported": true,
  "pairwise-interaction": true,
  "benchmark-evaluation": true,
  "proposal-target": true,
  hideUnrelatedMemories: false,
};

function summarizeDistribution(distribution: Record<string, number>): string {
  const parts = Object.entries(distribution).map(
    ([action, count]) => `${action} x${count}`,
  );
  return parts.length ? parts.join(", ") : "no action change recorded";
}

function getMemoryNodeHeight(memoryCount: number): number {
  return memoryCount <= 3 ? 124 : 112;
}

function buildMemoryNodes(memories: MemoryInfluenceMemoryEvidence[]): GraphNode[] {
  const startY = 88;
  const stepY = memories.length > 1 ? Math.max(130, 440 / Math.max(memories.length - 1, 1)) : 0;
  const height = getMemoryNodeHeight(memories.length);

  return memories.map((memory, index) => ({
    id: `memory:${memory.memoryId}`,
    type: "memory",
    label: memory.memoryId,
    x: 320,
    y: startY + index * stepY,
    width: 260,
    height,
    ariaLabel: `Memory ${memory.memoryId}`,
    memoryId: memory.memoryId,
  }));
}

export function buildGraphModel(data: MemoryInfluenceGraphEvidence): GraphModel {
  const memoryNodes = buildMemoryNodes(data.memories);
  const nodes: GraphNode[] = [
    {
      id: "user-request",
      type: "user-request",
      label: "User request",
      x: 32,
      y: 210,
      width: 220,
      height: 96,
      ariaLabel: "User request node",
    },
    ...memoryNodes,
    {
      id: "agent-decision",
      type: "agent-decision",
      label: data.originalAction ?? "Agent decision",
      x: 760,
      y: 120,
      width: 250,
      height: 110,
      ariaLabel: "Agent decision node",
    },
    {
      id: "tool-action",
      type: "tool-action",
      label: "Tool or control action",
      x: 760,
      y: 300,
      width: 250,
      height: 96,
      ariaLabel: "Tool or control action node",
    },
    {
      id: "evaluator-outcome",
      type: "evaluator-outcome",
      label: data.expectedAction ? `Expected ${data.expectedAction}` : "Evaluator outcome",
      x: 760,
      y: 474,
      width: 250,
      height: 108,
      ariaLabel: "Evaluator outcome node",
    },
  ];

  if (data.proposal) {
    nodes.push({
      id: "repair-proposal",
      type: "repair-proposal",
      label: data.proposal.repairType ?? "Repair proposal",
      x: 470,
      y: 620,
      width: 300,
      height: 104,
      ariaLabel: "Repair proposal node",
    });
  }

  const edges: GraphEdge[] = [];

  for (const memory of data.memories) {
    edges.push({
      id: `retrieval:${memory.memoryId}`,
      source: "user-request",
      target: `memory:${memory.memoryId}`,
      type: "observed-retrieval",
      label: "observed retrieval",
      detail: `${memory.memoryId} was included in the agent-visible snapshot.`,
      memoryIds: [memory.memoryId],
    });

    if (memory.observedCitation) {
      edges.push({
        id: `citation:${memory.memoryId}`,
        source: `memory:${memory.memoryId}`,
        target: "agent-decision",
        type: "agent-citation",
        label: "agent citation",
        detail: `${memory.memoryId} was cited in the structured response.`,
        memoryIds: [memory.memoryId],
      });
    }

    if (memory.strongestIndividualInfluence !== 0) {
      edges.push({
        id: `replay:${memory.memoryId}`,
        source: `memory:${memory.memoryId}`,
        target: "agent-decision",
        type: "replay-supported",
        label: "replay-supported influence",
        detail: `Observed influence delta ${memory.strongestIndividualInfluence.toFixed(2)} across individual replay interventions.`,
        memoryIds: [memory.memoryId],
      });
    }

    if (data.proposal?.targetMemoryIds.includes(memory.memoryId)) {
      edges.push({
        id: `proposal:${memory.memoryId}`,
        source: `memory:${memory.memoryId}`,
        target: "repair-proposal",
        type: "proposal-target",
        label: "proposal target",
        detail: `${memory.memoryId} is targeted by the recorded repair proposal.`,
        memoryIds: [memory.memoryId],
      });
    }
  }

  edges.push({
    id: "benchmark-evaluation",
    source: "agent-decision",
    target: "evaluator-outcome",
    type: "benchmark-evaluation",
    label: "benchmark-only evaluation",
    detail: `Actual action ${data.originalAction ?? "unknown"} compared against expected action ${data.expectedAction ?? "unknown"}.`,
    memoryIds: [],
  });

  if (data.proposal) {
    edges.push({
      id: "decision-to-tool",
      source: "agent-decision",
      target: "tool-action",
      type: "benchmark-evaluation",
      label: "control action",
      detail: "Structured output and control metadata were recorded for this run.",
      memoryIds: [],
    });
    edges.push({
      id: "proposal-summary",
      source: "evaluator-outcome",
      target: "repair-proposal",
      type: "benchmark-evaluation",
      label: "repair context",
      detail: data.proposal.conciseExplanation ?? "Proposal context available.",
      memoryIds: [],
    });
  }

  for (const memory of data.memories) {
    for (const supersededId of memory.supersedes) {
      edges.push({
        id: `supersedes:${memory.memoryId}:${supersededId}`,
        source: `memory:${memory.memoryId}`,
        target: `memory:${supersededId}`,
        type: "metadata-relationship",
        label: "metadata: supersedes",
        detail: `${memory.memoryId} supersedes ${supersededId} in the operational metadata.`,
        memoryIds: [memory.memoryId, supersededId],
      });
    }
  }

  for (const contradiction of data.contradictions) {
    const [memoryA, memoryB] = contradiction.memoryIds;
    if (contradiction.deterministicRelationship.relationship !== "unrelated") {
      edges.push({
        id: `metadata:${memoryA}:${memoryB}`,
        source: `memory:${memoryA}`,
        target: `memory:${memoryB}`,
        type: "metadata-relationship",
        label: `metadata: ${contradiction.deterministicRelationship.relationship}`,
        detail: contradiction.deterministicRelationship.conciseReason,
        memoryIds: [memoryA, memoryB],
      });
    }

    edges.push({
      id: `semantic:${memoryA}:${memoryB}`,
      source: `memory:${memoryA}`,
      target: `memory:${memoryB}`,
      type: "semantic-hypothesis",
      label: `semantic: ${contradiction.semanticRelationship.relationship}`,
      detail: contradiction.semanticRelationship.conciseExplanation,
      memoryIds: [memoryA, memoryB],
    });
  }

  for (const interaction of data.pairwiseInteractions) {
    const [memoryA, memoryB] = interaction.memoryIds;
    edges.push({
      id: `pairwise:${memoryA}:${memoryB}:${interaction.interventionType}`,
      source: `memory:${memoryA}`,
      target: `memory:${memoryB}`,
      type: "pairwise-interaction",
      label: "pairwise interaction",
      detail: `${interaction.evidenceClassification}; combined influence ${interaction.combinedInfluence.toFixed(2)}; actions ${summarizeDistribution(interaction.combinedActionDistribution)}.`,
      memoryIds: [memoryA, memoryB],
    });
  }

  return { nodes, edges };
}

export function filterGraphModel(
  model: GraphModel,
  filters: GraphFilters,
  selectedMemoryId: string | null,
): GraphModel {
  const visibleEdges = model.edges.filter((edge) => filters[edge.type]);

  if (!selectedMemoryId || !filters.hideUnrelatedMemories) {
    return {
      nodes: model.nodes,
      edges: visibleEdges,
    };
  }

  const relatedNodeIds = new Set<string>([
    "user-request",
    "agent-decision",
    "tool-action",
    "evaluator-outcome",
    "repair-proposal",
    `memory:${selectedMemoryId}`,
  ]);

  for (const edge of visibleEdges) {
    if (edge.memoryIds.includes(selectedMemoryId)) {
      relatedNodeIds.add(edge.source);
      relatedNodeIds.add(edge.target);
      for (const memoryId of edge.memoryIds) {
        relatedNodeIds.add(`memory:${memoryId}`);
      }
    }
  }

  const visibleNodes = model.nodes.filter((node) => {
    if (node.type !== "memory") {
      return true;
    }
    return relatedNodeIds.has(node.id);
  });

  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));

  return {
    nodes: visibleNodes,
    edges: visibleEdges.filter(
      (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target),
    ),
  };
}

export function getStrongestPairwiseFinding(
  interactions: MemoryInfluencePairwiseInteraction[],
): MemoryInfluencePairwiseInteraction | null {
  return (
    [...interactions].sort((left, right) => {
      const rightMagnitude =
        Math.abs(right.combinedInfluence) + Math.abs(right.interactionSynergy);
      const leftMagnitude =
        Math.abs(left.combinedInfluence) + Math.abs(left.interactionSynergy);
      return rightMagnitude - leftMagnitude;
    })[0] ?? null
  );
}

export function getMemoryDisplayFlags(memory: MemoryInfluenceMemoryEvidence): string[] {
  const flags: string[] = [];

  if (memory.deterministicSuspicionReasons.length) {
    flags.push("D");
  }
  if (memory.semanticIssueTypes.length || memory.semanticHypotheses.length) {
    flags.push("S");
  }
  if (memory.strongestIndividualInfluence !== 0) {
    flags.push("I");
  }
  if (memory.strongestInteractionInfluence !== 0) {
    flags.push("P");
  }

  return flags;
}
