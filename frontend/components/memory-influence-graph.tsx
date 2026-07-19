"use client";

import { useMemo, useState } from "react";

import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import type {
  MemoryInfluenceGraphEvidence,
  MemoryInfluenceMemoryEvidence,
} from "@/lib/benchmark-shared";
import {
  buildGraphModel,
  DEFAULT_GRAPH_FILTERS,
  filterGraphModel,
  getMemoryDisplayFlags,
  getStrongestPairwiseFinding,
  type GraphEdge,
  type GraphEdgeType,
  type GraphFilters,
  type GraphNode,
} from "@/lib/memory-influence-graph";
import { cn } from "@/lib/utils";

const EDGE_STYLES: Record<
  GraphEdgeType,
  { dash: string | null; marker: string; label: string }
> = {
  "observed-retrieval": {
    dash: null,
    marker: "OBS",
    label: "Observed retrieval",
  },
  "agent-citation": {
    dash: "10 6",
    marker: "CITE",
    label: "Agent citation",
  },
  "metadata-relationship": {
    dash: "4 4",
    marker: "META",
    label: "Metadata-derived",
  },
  "semantic-hypothesis": {
    dash: "2 8",
    marker: "HYP",
    label: "Semantic hypothesis",
  },
  "replay-supported": {
    dash: "18 8",
    marker: "REPLAY",
    label: "Replay-supported influence",
  },
  "pairwise-interaction": {
    dash: "14 6 2 6",
    marker: "PAIR",
    label: "Pairwise interaction",
  },
  "benchmark-evaluation": {
    dash: "1 10",
    marker: "EVAL",
    label: "Benchmark-only evaluation",
  },
  "proposal-target": {
    dash: "20 8",
    marker: "PROP",
    label: "Proposal target",
  },
};

function getNodeTone(node: GraphNode) {
  switch (node.type) {
    case "user-request":
      return "border-signal-info/35 bg-signal-info/10";
    case "memory":
      return "border-white/12 bg-surface-950/90";
    case "agent-decision":
      return "border-signal-semantic/35 bg-signal-semantic/10";
    case "tool-action":
      return "border-signal-replay/35 bg-signal-replay/10";
    case "evaluator-outcome":
      return "border-signal-warning/35 bg-signal-warning/10";
    case "repair-proposal":
      return "border-signal-concern/35 bg-signal-concern/10";
  }
}

function getEdgeColor(type: GraphEdgeType): string {
  switch (type) {
    case "observed-retrieval":
      return "var(--viz-series-2)";
    case "agent-citation":
      return "var(--viz-series-3)";
    case "metadata-relationship":
      return "var(--viz-series-4)";
    case "semantic-hypothesis":
      return "var(--viz-series-5)";
    case "replay-supported":
      return "var(--viz-series-1)";
    case "pairwise-interaction":
      return "var(--viz-series-6)";
    case "benchmark-evaluation":
      return "var(--foreground)";
    case "proposal-target":
      return "var(--accent-foreground)";
  }
}

function makeEdgePath(source: GraphNode, target: GraphNode): string {
  const sourceX = source.x + source.width;
  const sourceY = source.y + source.height / 2;
  const targetX = target.x;
  const targetY = target.y + target.height / 2;
  const midX = sourceX + (targetX - sourceX) / 2;
  return `M ${sourceX} ${sourceY} C ${midX} ${sourceY}, ${midX} ${targetY}, ${targetX} ${targetY}`;
}

function makeMemoryPairPath(source: GraphNode, target: GraphNode): string {
  const sourceX = source.x + source.width / 2;
  const sourceY = source.y + source.height;
  const targetX = target.x + target.width / 2;
  const targetY = target.y;
  const controlY = Math.max(sourceY, targetY) + 64;
  return `M ${sourceX} ${sourceY} C ${sourceX} ${controlY}, ${targetX} ${controlY}, ${targetX} ${targetY}`;
}

function formatDistribution(distribution: Record<string, number>) {
  return Object.entries(distribution)
    .map(([action, count]) => `${action} x${count}`)
    .join(", ");
}

function FilterCheckbox({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink-200">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="h-4 w-4 rounded border-white/20 bg-surface-950/90"
      />
      <span>{label}</span>
    </label>
  );
}

function NodeButton({
  node,
  memory,
  selected,
  scale,
  onSelect,
}: {
  node: GraphNode;
  memory: MemoryInfluenceMemoryEvidence | null;
  selected: boolean;
  scale: number;
  onSelect: (memoryId: string | null) => void;
}) {
  const flags = memory ? getMemoryDisplayFlags(memory) : [];

  return (
    <button
      type="button"
      aria-label={node.ariaLabel}
      onClick={() => onSelect(memory?.memoryId ?? null)}
      className={cn(
        "absolute rounded-xl border px-4 py-3 text-left shadow-panel transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal-info",
        getNodeTone(node),
        selected ? "ring-2 ring-signal-info" : "",
      )}
      style={{
        left: node.x * scale,
        top: node.y * scale,
        width: node.width * scale,
        minHeight: node.height * scale,
      }}
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-sm text-ink-50">{node.label}</span>
          {memory ? (
            <StatusBadge label={memory.freshnessState} tone={memory.freshnessState === "active" ? "success" : memory.freshnessState === "uncertain" ? "inconclusive" : memory.freshnessState === "invalid" ? "failure" : "warning"} />
          ) : null}
        </div>
        {memory ? (
          <>
            <p className="text-xs leading-5 text-ink-200">{memory.shortContent}</p>
            <div className="flex flex-wrap gap-2 text-[11px] text-ink-300">
              <span>priority {memory.retrievalPriority}</span>
              <span>confidence {memory.confidence.toFixed(2)}</span>
              {memory.suspicionRank ? <span>rank #{memory.suspicionRank}</span> : null}
            </div>
            <div className="flex flex-wrap gap-2">
              {flags.map((flag) => (
                <StatusBadge
                  key={flag}
                  label={flag}
                  tone={
                    flag === "D"
                      ? "warning"
                      : flag === "S"
                        ? "concern"
                        : flag === "I"
                          ? "success"
                          : "info"
                  }
                />
              ))}
            </div>
          </>
        ) : (
          <p className="text-xs leading-5 text-ink-200">
            {node.type === "agent-decision"
              ? "Observable structured decision output."
              : node.type === "tool-action"
                ? "Tool or control metadata recorded during execution."
                : node.type === "evaluator-outcome"
                  ? "Benchmark-only evaluation state."
                  : "Stored repair proposal context."}
          </p>
        )}
      </div>
    </button>
  );
}

function MemoryDetailPanel({
  memory,
}: {
  memory: MemoryInfluenceMemoryEvidence | null;
}) {
  if (!memory) {
    return (
      <div className="rounded-xl border border-white/10 bg-surface-950/70 p-4 text-sm text-ink-200">
        Select a memory node to inspect deterministic suspicion, semantic hypotheses, replay results, pairwise participation, contradictions, and proposal targeting.
      </div>
    );
  }

  const strongestPair = getStrongestPairwiseFinding(memory.pairwiseParticipation);

  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-surface-950/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-ink-50">{memory.memoryId}</span>
        <StatusBadge label={memory.freshnessState} tone={memory.freshnessState === "active" ? "success" : memory.freshnessState === "uncertain" ? "inconclusive" : memory.freshnessState === "invalid" ? "failure" : "warning"} />
        {memory.proposalTargeted ? <StatusBadge label="proposal targeted" tone="concern" /> : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Operational metadata</p>
          <p className="mt-2">Source: {memory.source}</p>
          <p className="mt-1 font-mono text-xs">{memory.entityId}</p>
          <p className="mt-1">Priority: {memory.retrievalPriority}</p>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Observed evidence</p>
          <p className="mt-2">Retrieved: {String(memory.observedRetrieval)}</p>
          <p className="mt-1">Cited: {String(memory.observedCitation)}</p>
          <p className="mt-1">Strongest individual delta: {memory.strongestIndividualInfluence.toFixed(2)}</p>
          <p className="mt-1">Strongest pair delta: {memory.strongestInteractionInfluence.toFixed(2)}</p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Deterministic suspicion reasons</p>
          <ul className="mt-2 space-y-2">
            {memory.deterministicSuspicionReasons.length ? (
              memory.deterministicSuspicionReasons.map((reason) => <li key={reason}>{reason}</li>)
            ) : (
              <li>No deterministic suspicion reasons were recorded.</li>
            )}
          </ul>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Semantic suspicion reasons</p>
          <ul className="mt-2 space-y-2">
            {memory.semanticHypotheses.length || memory.semanticSuspicionReasons.length ? (
              [...memory.semanticHypotheses, ...memory.semanticSuspicionReasons].map((reason) => (
                <li key={reason}>{reason}</li>
              ))
            ) : (
              <li>No semantic suspicion reasons were recorded.</li>
            )}
          </ul>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Replay results</p>
          <ul className="mt-2 space-y-2">
            {memory.individualReplayResults.length ? (
              memory.individualReplayResults.map((result) => (
                <li key={`${result.interventionType}-${result.targetMemoryIds.join("-")}`}>
                  {result.interventionType}: delta {result.influenceDelta.toFixed(2)}; {formatDistribution(result.actionDistribution)}
                </li>
              ))
            ) : (
              <li>No individual replay results recorded for this memory.</li>
            )}
          </ul>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Pairwise participation</p>
          <ul className="mt-2 space-y-2">
            {memory.pairwiseParticipation.length ? (
              memory.pairwiseParticipation.map((pair) => (
                <li key={`${pair.memoryIds.join("-")}-${pair.interventionType}`}>
                  {pair.memoryIds.join(" + ")}: combined {pair.combinedInfluence.toFixed(2)}, interaction {pair.interactionScore.toFixed(2)}, synergy {pair.interactionSynergy.toFixed(2)}
                </li>
              ))
            ) : (
              <li>No pairwise replay evidence recorded for this memory.</li>
            )}
          </ul>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Contradictions and relationships</p>
          <ul className="mt-2 space-y-2">
            {memory.contradictionRelationships.length ? (
              memory.contradictionRelationships.map((relationship) => (
                <li key={relationship.memoryIds.join("-")}>
                  {relationship.memoryIds.join(" / ")}: {relationship.semanticRelationship.conciseExplanation}
                </li>
              ))
            ) : (
              <li>No contradiction relationships recorded for this memory.</li>
            )}
          </ul>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Support-validity audit</p>
          <ul className="mt-2 space-y-2">
            {memory.supportValidityAudit.length ? (
              memory.supportValidityAudit.map((item) => <li key={item}>{item}</li>)
            ) : (
              <li>No memory-specific support-validity notes were recorded.</li>
            )}
            {strongestPair ? (
              <li>
                Strongest pair: {strongestPair.memoryIds.join(" + ")}; supported{" "}
                {String(strongestPair.supportValid)}.
              </li>
            ) : null}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function MemoryInfluenceGraph({
  data,
}: {
  data: MemoryInfluenceGraphEvidence;
}) {
  const [scale, setScale] = useState(1);
  const [filters, setFilters] = useState<GraphFilters>(DEFAULT_GRAPH_FILTERS);
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(
    data.memories[0]?.memoryId ?? null,
  );

  const model = useMemo(() => buildGraphModel(data), [data]);
  const filteredModel = useMemo(
    () => filterGraphModel(model, filters, selectedMemoryId),
    [filters, model, selectedMemoryId],
  );

  const nodeMap = useMemo(
    () => new Map(filteredModel.nodes.map((node) => [node.id, node])),
    [filteredModel.nodes],
  );
  const memoryMap = useMemo(
    () => new Map(data.memories.map((memory) => [memory.memoryId, memory])),
    [data.memories],
  );

  const selectedMemory = selectedMemoryId ? memoryMap.get(selectedMemoryId) ?? null : null;

  const visibleEdgeRows = filteredModel.edges.map((edge) => ({
    ...edge,
    evidenceLabel: EDGE_STYLES[edge.type].label,
  }));

  return (
    <SectionCard title="Memory Influence Graph" eyebrow="Observed retrieval, hypotheses, and replay evidence">
      <div className="space-y-6">
        <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setScale((value) => Math.min(1.4, Number((value + 0.1).toFixed(2))))}
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Zoom in
              </button>
              <button
                type="button"
                onClick={() => setScale((value) => Math.max(0.75, Number((value - 0.1).toFixed(2))))}
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Zoom out
              </button>
              <button
                type="button"
                onClick={() => setScale(1)}
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Fit view
              </button>
              <button
                type="button"
                onClick={() => {
                  setScale(1);
                  setFilters(DEFAULT_GRAPH_FILTERS);
                  setSelectedMemoryId(data.memories[0]?.memoryId ?? null);
                }}
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Reset
              </button>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {(
                Object.keys(EDGE_STYLES) as GraphEdgeType[]
              ).map((edgeType) => (
                <FilterCheckbox
                  key={edgeType}
                  checked={filters[edgeType]}
                  label={EDGE_STYLES[edgeType].label}
                  onChange={() =>
                    setFilters((current) => ({
                      ...current,
                      [edgeType]: !current[edgeType],
                    }))
                  }
                />
              ))}
              <FilterCheckbox
                checked={filters.hideUnrelatedMemories}
                label="Hide unrelated memories"
                onChange={() =>
                  setFilters((current) => ({
                    ...current,
                    hideUnrelatedMemories: !current.hideUnrelatedMemories,
                  }))
                }
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() =>
                  setFilters({
                    ...DEFAULT_GRAPH_FILTERS,
                    "observed-retrieval": false,
                    "agent-citation": false,
                    "metadata-relationship": false,
                    "semantic-hypothesis": false,
                    "benchmark-evaluation": false,
                    "proposal-target": false,
                  })
                }
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Show only replay-supported edges
              </button>
              <button
                type="button"
                onClick={() =>
                  setFilters({
                    ...DEFAULT_GRAPH_FILTERS,
                    "observed-retrieval": false,
                    "agent-citation": false,
                    "semantic-hypothesis": false,
                    "replay-supported": false,
                    "pairwise-interaction": false,
                    "benchmark-evaluation": false,
                    "proposal-target": false,
                  })
                }
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Show only metadata relationships
              </button>
              <button
                type="button"
                onClick={() =>
                  setFilters({
                    ...DEFAULT_GRAPH_FILTERS,
                    "observed-retrieval": false,
                    "agent-citation": false,
                    "metadata-relationship": false,
                    "replay-supported": false,
                    "pairwise-interaction": false,
                    "benchmark-evaluation": false,
                    "proposal-target": false,
                  })
                }
                className="rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                Show semantic hypotheses
              </button>
            </div>

            <div className="overflow-x-auto rounded-xl border border-white/10 bg-surface-950/70 p-3">
              <div
                className="relative"
                style={{
                  width: 1080 * scale,
                  height: 760 * scale,
                  minWidth: "100%",
                }}
              >
                <svg
                  width={1080 * scale}
                  height={760 * scale}
                  viewBox={`0 0 ${1080 * scale} ${760 * scale}`}
                  role="img"
                  aria-label={`Memory influence graph for ${data.scenarioId}`}
                  className="absolute inset-0"
                >
                  {filteredModel.edges.map((edge) => {
                    const source = nodeMap.get(edge.source);
                    const target = nodeMap.get(edge.target);
                    if (!source || !target) {
                      return null;
                    }

                    const isMemoryPair =
                      source.type === "memory" && target.type === "memory";
                    const path = isMemoryPair
                      ? makeMemoryPairPath(source, target)
                      : makeEdgePath(source, target);
                    const style = EDGE_STYLES[edge.type];
                    const labelX = ((source.x + source.width) + target.x) / 2 * scale;
                    const labelY = ((source.y + source.height / 2) + (target.y + target.height / 2)) / 2 * scale;

                    return (
                      <g key={edge.id}>
                        <path
                          d={path}
                          fill="none"
                          stroke={getEdgeColor(edge.type)}
                          strokeWidth={edge.type === "pairwise-interaction" ? 3 : 2}
                          strokeDasharray={style.dash ?? undefined}
                          opacity={0.95}
                          transform={`scale(${scale})`}
                        />
                        <rect
                          x={labelX - 36}
                          y={labelY - 11}
                          width={72}
                          height={22}
                          rx={11}
                          fill="var(--card)"
                          stroke="var(--border)"
                        />
                        <text
                          x={labelX}
                          y={labelY + 4}
                          textAnchor="middle"
                          fontSize="10"
                          fill="var(--card-foreground)"
                        >
                          {style.marker}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {filteredModel.nodes.map((node) => (
                  <NodeButton
                    key={node.id}
                    node={node}
                    memory={node.memoryId ? memoryMap.get(node.memoryId) ?? null : null}
                    selected={node.memoryId === selectedMemoryId}
                    scale={scale}
                    onSelect={setSelectedMemoryId}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-surface-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Evidence legend</p>
              <div className="mt-3 space-y-3 text-sm text-ink-200">
                {(Object.keys(EDGE_STYLES) as GraphEdgeType[]).map((edgeType) => (
                  <div key={edgeType} className="flex items-start gap-3">
                    <StatusBadge label={EDGE_STYLES[edgeType].marker} tone={edgeType === "replay-supported" ? "success" : edgeType === "semantic-hypothesis" ? "concern" : edgeType === "metadata-relationship" ? "warning" : edgeType === "pairwise-interaction" ? "info" : "neutral"} />
                    <div>
                      <p className="text-ink-100">{EDGE_STYLES[edgeType].label}</p>
                      <p className="text-xs text-ink-300">
                        {edgeType === "semantic-hypothesis"
                          ? "Model-suggested relationship only; not proof of causality."
                          : edgeType === "benchmark-evaluation"
                            ? "Benchmark-only answer-key comparison."
                            : edgeType === "pairwise-interaction"
                              ? "Observed combined intervention result."
                              : edgeType === "replay-supported"
                                ? "Observed action change under controlled replay."
                                : edgeType === "metadata-relationship"
                                  ? "Operational metadata or contradiction record."
                                  : edgeType === "agent-citation"
                                    ? "Explicitly cited in structured output."
                                    : "Included in the selected snapshot."}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-surface-950/70 p-4 text-sm text-ink-200">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Scenario findings</p>
              <p className="mt-3">Classification: {data.classification ?? "not recorded"}</p>
              <p className="mt-2">No-memory control preserved wrong action: {String(data.noMemoryControlPreservedWrongAction)}</p>
              {data.supportValiditySummary ? <p className="mt-2">{data.supportValiditySummary}</p> : null}
            </div>

            <MemoryDetailPanel memory={selectedMemory} />
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-surface-950/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Alternative evidence table</p>
            <StatusBadge label={`${visibleEdgeRows.length} visible edges`} tone="info" />
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2 text-left text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-[0.22em] text-ink-300">
                  <th className="pr-4">Evidence type</th>
                  <th className="pr-4">Label</th>
                  <th className="pr-4">Memories</th>
                  <th className="pr-4">Detail</th>
                </tr>
              </thead>
              <tbody>
                {visibleEdgeRows.map((edge) => (
                  <tr key={edge.id} className="bg-white/[0.03] text-ink-100">
                    <td className="rounded-l-lg border-y border-l border-white/8 px-3 py-3">
                      {edge.evidenceLabel}
                    </td>
                    <td className="border-y border-white/8 px-3 py-3">{edge.label}</td>
                    <td className="border-y border-white/8 px-3 py-3 font-mono text-xs">
                      {edge.memoryIds.length ? edge.memoryIds.join(", ") : "n/a"}
                    </td>
                    <td className="rounded-r-lg border-y border-r border-white/8 px-3 py-3 text-ink-200">
                      {edge.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
