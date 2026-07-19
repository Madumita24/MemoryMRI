"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { DomainBadge } from "@/components/domain-badge";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import { apiClient, ApiClientError } from "@/lib/api/client";
import type {
  ReplayLabComparisonCard,
  ReplayLabControlResult,
  ReplayLabEvidence,
  ReplayLabEvidenceLink,
  ReplayLabIndividualResult,
  ReplayLabPairwiseResult,
} from "@/lib/benchmark-shared";
import { getDomainLabel, toSentenceCase } from "@/lib/benchmark-shared";
import { getPublicEnvResult } from "@/lib/env";

function toneForSupport(value: boolean | null) {
  if (value === true) {
    return "success" as const;
  }
  if (value === false) {
    return "warning" as const;
  }
  return "neutral" as const;
}

function formatRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDistribution(distribution: Record<string, number>): string {
  const entries = Object.entries(distribution);
  if (!entries.length) {
    return "none";
  }
  return entries.map(([action, count]) => `${action}: ${count}`).join(", ");
}

function EvidenceLinkChip({ item }: { item: ReplayLabEvidenceLink }) {
  if (!item.href) {
    return (
      <span className="inline-flex rounded-full border border-white/8 px-3 py-2 text-sm text-ink-400">
        {item.label} unavailable
      </span>
    );
  }

  const isFile = item.href.startsWith("file:///");

  if (isFile) {
    return (
      <a
        href={item.href}
        className="inline-flex rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
      >
        {item.label}
      </a>
    );
  }

  return (
    <Link
      href={item.href}
      className="inline-flex rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
    >
      {item.label}
    </Link>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
      <p className="text-xs uppercase tracking-[0.22em] text-ink-300">{label}</p>
      <p className="mt-2 text-lg font-semibold text-ink-50">{value}</p>
      {detail ? <p className="mt-2 text-sm text-ink-300">{detail}</p> : null}
    </div>
  );
}

function ResultMetricGrid({
  result,
}: {
  result: ReplayLabIndividualResult | ReplayLabPairwiseResult | ReplayLabControlResult;
}) {
  if ("memoryId" in result) {
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Original success" value={formatRate(result.originalSuccessRate)} />
        <MetricCard
          label="Intervention success"
          value={formatRate(result.interventionSuccessRate)}
        />
        <MetricCard label="Influence delta" value={result.influenceDelta.toFixed(2)} />
        <MetricCard
          label="Wilson interval"
          value={`${result.wilsonLow.toFixed(2)} to ${result.wilsonHigh.toFixed(2)}`}
        />
      </div>
    );
  }

  if ("memoryIds" in result) {
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Influence A" value={result.influenceA.toFixed(2)} />
        <MetricCard label="Influence B" value={result.influenceB.toFixed(2)} />
        <MetricCard label="Combined" value={result.combinedInfluence.toFixed(2)} />
        <MetricCard label="Interaction" value={result.interactionScore.toFixed(2)} />
        <MetricCard label="Synergy" value={result.interactionSynergy.toFixed(2)} />
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Original success" value={formatRate(result.originalSuccessRate)} />
      <MetricCard label="Control success" value={formatRate(result.controlSuccessRate)} />
      <MetricCard label="Replay stability" value={result.replayStability.toFixed(2)} />
      <MetricCard
        label="Infrastructure errors"
        value={String(result.infrastructureErrorCount)}
      />
    </div>
  );
}

function ComparisonPanel({ cards }: { cards: ReplayLabComparisonCard[] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-ink-50">{card.label}</p>
            <StatusBadge label={card.status} tone={toneForSupport(card.supportValid)} />
          </div>
          <p className="mt-3 text-sm leading-6 text-ink-200">{card.summary}</p>
          <p className="mt-3 text-xs uppercase tracking-[0.22em] text-ink-300">Action distribution</p>
          <p className="mt-2 text-sm text-ink-100">{formatDistribution(card.actionDistribution)}</p>
        </div>
      ))}
    </div>
  );
}

function ResultLinks({
  traceLinks,
  artifactLinks,
}: {
  traceLinks: ReplayLabEvidenceLink[];
  artifactLinks?: ReplayLabEvidenceLink[];
}) {
  return (
    <div className="flex flex-wrap gap-3">
      {traceLinks.map((item) => (
        <EvidenceLinkChip key={`${item.label}-${item.href ?? "missing"}`} item={item} />
      ))}
      {(artifactLinks ?? []).map((item) => (
        <EvidenceLinkChip key={`${item.label}-${item.href ?? "missing"}`} item={item} />
      ))}
    </div>
  );
}

function IndividualResultCard({ result }: { result: ReplayLabIndividualResult }) {
  return (
    <div className="space-y-4 rounded-2xl border border-white/8 bg-surface-950/70 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-ink-50">{result.memoryId}</span>
            <StatusBadge label={result.interventionType} tone="replay" />
            <StatusBadge label={`${result.runCount} run(s)`} tone="info" />
          </div>
          <p className="text-sm text-ink-200">
            Original {formatDistribution(result.originalActionDistribution)}. Intervention{" "}
            {formatDistribution(result.interventionActionDistribution)}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={`support ${String(result.supportValid)}`} tone={toneForSupport(result.supportValid)} />
          {result.requiresHumanReview ? (
            <StatusBadge label="needs review" tone="warning" />
          ) : null}
        </div>
      </div>
      <ResultMetricGrid result={result} />
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Replay stability</p>
          <p className="mt-2">Original {result.originalReplayStability.toFixed(2)}</p>
          <p className="mt-1">Intervention {result.interventionReplayStability.toFixed(2)}</p>
          <p className="mt-3 text-xs uppercase tracking-[0.22em] text-ink-300">Errors</p>
          <p className="mt-2">
            Original: {result.originalErrors.length ? result.originalErrors.join("; ") : "none"}
          </p>
          <p className="mt-1">
            Intervention: {result.interventionErrors.length ? result.interventionErrors.join("; ") : "none"}
          </p>
        </div>
        <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Support validity</p>
          <p className="mt-2 leading-6 text-ink-100">
            {result.supportExplanation ?? "No support-validity note was stored."}
          </p>
        </div>
      </div>
      <ResultLinks traceLinks={result.traceLinks} artifactLinks={result.artifactLinks} />
    </div>
  );
}

function PairwiseResultCard({ result }: { result: ReplayLabPairwiseResult }) {
  return (
    <div className="space-y-4 rounded-2xl border border-white/8 bg-surface-950/70 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-ink-50">
              {result.memoryIds[0]} + {result.memoryIds[1]}
            </span>
            <StatusBadge label={result.interventionType} tone="replay" />
            <StatusBadge label={result.evidenceClassification} tone="semantic" />
          </div>
          <p className="text-sm text-ink-200">
            Combined action distribution {formatDistribution(result.combinedActionDistribution)}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={`support ${String(result.supportValid)}`} tone={toneForSupport(result.supportValid)} />
          {result.requiresHumanReview ? (
            <StatusBadge label="needs review" tone="warning" />
          ) : null}
        </div>
      </div>
      <ResultMetricGrid result={result} />
      <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
        <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Interpretation</p>
        <p className="mt-2 leading-6 text-ink-100">{result.supportExplanation}</p>
        <p className="mt-3">Infrastructure errors: {result.infrastructureErrorCount}</p>
      </div>
      <ResultLinks traceLinks={result.traceLinks} artifactLinks={result.artifactLinks} />
    </div>
  );
}

function ControlResultCard({ result }: { result: ReplayLabControlResult }) {
  return (
    <div className="space-y-4 rounded-2xl border border-white/8 bg-surface-950/70 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={result.controlType} tone="replay" />
            {result.targetMemoryId ? (
              <span className="font-mono text-sm text-ink-50">{result.targetMemoryId}</span>
            ) : null}
          </div>
          <p className="text-sm text-ink-200">
            Original {formatDistribution(result.originalActionDistribution)}. Control{" "}
            {formatDistribution(result.controlActionDistribution)}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={`support ${String(result.supportValid)}`} tone={toneForSupport(result.supportValid)} />
          {result.requiresHumanReview ? (
            <StatusBadge label="needs review" tone="warning" />
          ) : null}
        </div>
      </div>
      <ResultMetricGrid result={result} />
      <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
        <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Support validity</p>
        <p className="mt-2 leading-6 text-ink-100">{result.supportExplanation}</p>
      </div>
      <ResultLinks traceLinks={result.traceLinks} />
    </div>
  );
}

type LiveRunState =
  | "ready"
  | "awaiting confirmation"
  | "running"
  | "completed"
  | "partially completed"
  | "infrastructure error"
  | "inconclusive";

type PendingRunKind = "individual" | "pairwise" | null;

export function ReplayLaboratory({ data }: { data: ReplayLabEvidence }) {
  const router = useRouter();
  const env = getPublicEnvResult();
  const liveRunsEnabled = env.ok ? env.value.enableLiveRuns : false;
  const [selectedMemoryId, setSelectedMemoryId] = useState(
    data.individualResults[0]?.memoryId ?? data.snapshot[0]?.memoryId ?? "",
  );
  const [selectedPairA, setSelectedPairA] = useState(
    data.pairwiseResults[0]?.memoryIds[0] ?? data.snapshot[0]?.memoryId ?? "",
  );
  const [selectedPairB, setSelectedPairB] = useState(
    data.pairwiseResults[0]?.memoryIds[1] ??
      data.snapshot[1]?.memoryId ??
      data.snapshot[0]?.memoryId ??
      "",
  );
  const [selectedIndividualOperation, setSelectedIndividualOperation] = useState<"REMOVE_MEMORY" | "DISABLE_MEMORY">("REMOVE_MEMORY");
  const [selectedPairMode, setSelectedPairMode] = useState<"REMOVE_MEMORIES" | "DISABLE_MEMORIES" | "ALL_EXISTING_PAIRS">("ALL_EXISTING_PAIRS");
  const [liveRunState, setLiveRunState] = useState<LiveRunState>("ready");
  const [liveRunMessage, setLiveRunMessage] = useState<string | null>(null);
  const [pendingRunKind, setPendingRunKind] = useState<PendingRunKind>(null);

  const selectedIndividualResult = useMemo(
    () =>
      data.individualResults.find(
        (result) =>
          result.memoryId === selectedMemoryId &&
          result.interventionType === selectedIndividualOperation,
      ) ?? data.individualResults[0] ?? null,
    [data.individualResults, selectedIndividualOperation, selectedMemoryId],
  );

  const selectedPairResult = useMemo(() => {
    if (selectedPairMode === "ALL_EXISTING_PAIRS") {
      return data.pairwiseResults[0] ?? null;
    }
    return (
      data.pairwiseResults.find((result) => {
        const samePair =
          result.memoryIds.includes(selectedPairA) && result.memoryIds.includes(selectedPairB);
        return samePair && result.interventionType === selectedPairMode;
      }) ?? data.pairwiseResults[0] ?? null
    );
  }, [data.pairwiseResults, selectedPairA, selectedPairB, selectedPairMode]);

  const comparisonCards = useMemo<ReplayLabComparisonCard[]>(() => {
    const cards: ReplayLabComparisonCard[] = [
      {
        label: "Original",
        status: "original",
        summary: `Stored original benchmark action: ${data.originalAction ?? "unknown"}.`,
        actionDistribution:
          selectedIndividualResult?.originalActionDistribution ??
          data.noMemoryControl?.originalActionDistribution ??
          {},
        supportValid: null,
      },
    ];

    if (selectedIndividualResult) {
      cards.push({
        label: "Individual intervention",
        status: "intervention",
        summary: `${selectedIndividualResult.interventionType} on ${selectedIndividualResult.memoryId} changed success by ${selectedIndividualResult.influenceDelta.toFixed(2)}.`,
        actionDistribution: selectedIndividualResult.interventionActionDistribution,
        supportValid: selectedIndividualResult.supportValid,
      });
    }

    if (selectedPairResult) {
      cards.push({
        label: "Pair intervention",
        status: "intervention",
        summary: `${selectedPairResult.evidenceClassification} with interaction ${selectedPairResult.interactionScore.toFixed(2)}.`,
        actionDistribution: selectedPairResult.combinedActionDistribution,
        supportValid: selectedPairResult.supportValid,
      });
    }

    if (data.noMemoryControl) {
      cards.push({
        label: "Control result",
        status: "control",
        summary: data.noMemoryControl.supportExplanation,
        actionDistribution: data.noMemoryControl.controlActionDistribution,
        supportValid: data.noMemoryControl.supportValid,
      });
    }

    return cards;
  }, [data.noMemoryControl, data.originalAction, selectedIndividualResult, selectedPairResult]);

  const individualMutation = useMutation({
    mutationFn: async () => {
      const operation = selectedIndividualOperation === "REMOVE_MEMORY" ? "remove" : "disable";
      return apiClient.runIndividualReplay(data.investigationId, {
        operation,
        memory_id: selectedMemoryId,
      });
    },
    onMutate: () => {
      setLiveRunState("running");
      setLiveRunMessage(null);
    },
    onSuccess: () => {
      setLiveRunState("completed");
      setLiveRunMessage("Live replay completed. Refreshing the preserved evidence view.");
      router.refresh();
    },
    onError: (error) => {
      const message =
        error instanceof ApiClientError ? error.message : "The live replay request failed.";
      setLiveRunState("infrastructure error");
      setLiveRunMessage(message);
    },
  });

  const pairwiseMutation = useMutation({
    mutationFn: async () => {
      if (selectedPairMode === "ALL_EXISTING_PAIRS") {
        return apiClient.runPairwiseReplay(data.investigationId, {
          all_pairs: true,
          shared_baseline_runs: true,
          fresh_baseline_per_pair: false,
        });
      }

      return apiClient.runPairwiseReplay(data.investigationId, {
        memory_a: selectedPairA,
        memory_b: selectedPairB,
        all_pairs: false,
        shared_baseline_runs: true,
        fresh_baseline_per_pair: false,
      });
    },
    onMutate: () => {
      setLiveRunState("running");
      setLiveRunMessage(null);
    },
    onSuccess: () => {
      setLiveRunState("completed");
      setLiveRunMessage("Pairwise replay completed. Refreshing the preserved evidence view.");
      router.refresh();
    },
    onError: (error) => {
      const message =
        error instanceof ApiClientError ? error.message : "The pairwise replay request failed.";
      setLiveRunState("infrastructure error");
      setLiveRunMessage(message);
    },
  });

  const gptGuardrailMessage =
    "Runner GPT-5.6, default run count 3, cache disabled during replay, repeated model runs may incur cost.";

  const beginLiveRun = () => {
    setLiveRunState("awaiting confirmation");
    setLiveRunMessage(gptGuardrailMessage);
  };

  const confirmLiveRun = async () => {
    if (pendingRunKind === "individual") {
      await individualMutation.mutateAsync();
      setPendingRunKind(null);
      return;
    }
    if (pendingRunKind === "pairwise") {
      await pairwiseMutation.mutateAsync();
      setPendingRunKind(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Replay Laboratory"
        description={`Preserved replay evidence for ${data.scenarioId}. New experiments stay opt-in and cost-aware.`}
      />

      <SectionCard id="investigation-context" title="Investigation Context" eyebrow="Replay overview">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg text-ink-50">{data.investigationId}</span>
            <DomainBadge domain={data.domain} />
            <StatusBadge label={data.runnerLabel} tone="semantic" />
            {data.memoryDependenceClassification ? (
              <StatusBadge label={data.memoryDependenceClassification} tone="info" />
            ) : null}
            {data.verificationVerdict ? (
              <StatusBadge label={data.verificationVerdict} tone="inconclusive" />
            ) : null}
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Scenario" value={data.scenarioId} detail={data.title} />
            <MetricCard label="Domain" value={getDomainLabel(data.domain)} />
            <MetricCard label="Requested model" value={data.requestedModel} detail={`Returned ${data.responseModel}`} />
            <MetricCard label="Prompt version" value={data.promptVersion} detail={data.promptContentHash ?? "prompt-content hash unavailable"} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Original action</p>
              <p className="mt-2 font-mono text-sm text-ink-100">{data.originalAction ?? "n/a"}</p>
            </div>
            <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Expected action</p>
              <p className="mt-2 font-mono text-sm text-ink-100">
                {data.benchmarkMode ? data.expectedAction ?? "n/a" : "Hidden outside evaluation mode"}
              </p>
            </div>
          </div>
          <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
            <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Cache behavior</p>
            <p className="mt-2">{data.cachePolicy}</p>
            <div className="mt-3">
              {data.latestTimestamp ? <Timestamp value={data.latestTimestamp} /> : "No timestamp available"}
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard id="investigation-findings" title="Investigation Findings" eyebrow="Preserved evidence summary">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {data.suspiciousMemoryIds.map((memoryId) => (
              <StatusBadge key={memoryId} label={`suspicious ${memoryId}`} tone="warning" />
            ))}
            {data.contradictionPairs.map((pair) => (
              <StatusBadge key={pair} label={`contradiction ${pair}`} tone="concern" />
            ))}
          </div>
          <div className="grid gap-3">
            {data.highlightedFindings.map((finding) => (
              <div key={finding} className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm leading-6 text-ink-100">
                {finding}
              </div>
            ))}
          </div>
          {data.supportValiditySummary ? (
            <div className="rounded-xl border border-signal-warning/35 bg-signal-warning/10 p-4 text-sm leading-6 text-ink-100">
              {data.supportValiditySummary}
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard id="individual-replay" title="Individual Replay" eyebrow="Preserved results first">
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-3">
            <label className="space-y-2 text-sm text-ink-200">
              <span className="block text-xs uppercase tracking-[0.22em] text-ink-300">Memory</span>
              <select
                value={selectedMemoryId}
                onChange={(event) => setSelectedMemoryId(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-surface-950 px-3 py-2 text-ink-100"
              >
                {data.snapshot.map((memory) => (
                  <option key={memory.memoryId} value={memory.memoryId}>
                    {memory.memoryId}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm text-ink-200">
              <span className="block text-xs uppercase tracking-[0.22em] text-ink-300">Operation</span>
              <select
                value={selectedIndividualOperation}
                onChange={(event) =>
                  setSelectedIndividualOperation(
                    event.target.value as "REMOVE_MEMORY" | "DISABLE_MEMORY",
                  )
                }
                className="w-full rounded-xl border border-white/10 bg-surface-950 px-3 py-2 text-ink-100"
              >
                <option value="REMOVE_MEMORY">REMOVE_MEMORY</option>
                <option value="DISABLE_MEMORY">DISABLE_MEMORY</option>
                <option disabled>LOWER_RETRIEVAL_PRIORITY (not yet wired)</option>
                <option disabled>MARK_SUPERSEDED (not yet wired)</option>
                <option disabled>REPLACE_MEMORY_WITH_CANDIDATE (not yet wired)</option>
              </select>
            </label>
            <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Live mode</p>
              <p className="mt-2">
                {liveRunsEnabled
                  ? "Explicit GPT-backed replay is available."
                  : "Preserved evidence only. Live GPT replay is disabled in this environment."}
              </p>
            </div>
          </div>
          {selectedIndividualResult ? (
            <IndividualResultCard result={selectedIndividualResult} />
          ) : (
            <p className="text-sm text-ink-200">No preserved individual replay result matches this selection.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard id="pairwise-replay" title="Pairwise Replay" eyebrow="Interaction analysis">
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-4">
            <label className="space-y-2 text-sm text-ink-200">
              <span className="block text-xs uppercase tracking-[0.22em] text-ink-300">Pair mode</span>
              <select
                value={selectedPairMode}
                onChange={(event) =>
                  setSelectedPairMode(
                    event.target.value as
                      | "REMOVE_MEMORIES"
                      | "DISABLE_MEMORIES"
                      | "ALL_EXISTING_PAIRS",
                  )
                }
                className="w-full rounded-xl border border-white/10 bg-surface-950 px-3 py-2 text-ink-100"
              >
                <option value="ALL_EXISTING_PAIRS">ALL_EXISTING_PAIRS</option>
                <option value="REMOVE_MEMORIES">REMOVE_MEMORIES</option>
                <option value="DISABLE_MEMORIES">DISABLE_MEMORIES</option>
              </select>
            </label>
            <label className="space-y-2 text-sm text-ink-200">
              <span className="block text-xs uppercase tracking-[0.22em] text-ink-300">Memory A</span>
              <select
                value={selectedPairA}
                onChange={(event) => setSelectedPairA(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-surface-950 px-3 py-2 text-ink-100"
              >
                {data.snapshot.map((memory) => (
                  <option key={memory.memoryId} value={memory.memoryId}>
                    {memory.memoryId}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm text-ink-200">
              <span className="block text-xs uppercase tracking-[0.22em] text-ink-300">Memory B</span>
              <select
                value={selectedPairB}
                onChange={(event) => setSelectedPairB(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-surface-950 px-3 py-2 text-ink-100"
              >
                {data.snapshot.map((memory) => (
                  <option key={memory.memoryId} value={memory.memoryId}>
                    {memory.memoryId}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Safeguard</p>
              <p className="mt-2">Suspicion scores are not treated as proof of causal influence.</p>
            </div>
          </div>
          {selectedPairResult ? (
            <PairwiseResultCard result={selectedPairResult} />
          ) : (
            <p className="text-sm text-ink-200">No preserved pairwise replay result matches this selection.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard id="control-experiments" title="Control Experiments" eyebrow="Memory dependence checks">
        <div className="space-y-5">
          {data.noMemoryControl ? <ControlResultCard result={data.noMemoryControl} /> : null}
          <div className="grid gap-4">
            {data.isolationControls.map((result) => (
              <ControlResultCard key={`${result.controlType}-${result.targetMemoryId}`} result={result} />
            ))}
          </div>
          {data.scenarioId === "exp_09" ? (
            <div className="rounded-xl border border-signal-info/35 bg-signal-info/10 p-4 text-sm leading-6 text-ink-100">
              Incorrect behavior persisted with no memories, indicating that prompt or policy interpretation is a stronger hypothesis than memory influence.
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard id="evidence-comparison" title="Evidence Comparison" eyebrow="Compare original, intervention, and control">
        <div className="space-y-4">
          <ComparisonPanel cards={comparisonCards} />
          <p className="text-sm leading-6 text-ink-300">
            Suspicion may disagree with replay. Action changes may remain unsupported. Null effects are still meaningful evidence.
          </p>
        </div>
      </SectionCard>

      <SectionCard id="snapshot" title="Snapshot" eyebrow="Original agent-visible memory snapshot">
        <div className="space-y-4">
          {data.snapshot.map((memory) => (
            <div key={memory.memoryId} className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <span className="font-mono text-sm text-ink-50">{memory.memoryId}</span>
                    <StatusBadge label={memory.status} tone={toneForSupport(memory.status === "active")} />
                    {memory.analysisFlags.map((flag) => (
                      <StatusBadge key={flag} label={flag} tone="warning" />
                    ))}
                  </div>
                  <p className="text-sm text-ink-200">{memory.content}</p>
                </div>
                <div className="text-right text-xs text-ink-300">
                  <p>priority {memory.retrievalPriority}</p>
                  <p>confidence {memory.confidence.toFixed(2)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard id="live-run-safety" title="Live Run Safety" eyebrow="Explicit cost gate">
        <div className="space-y-4">
          <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm leading-6 text-ink-200">
            <p>Run state: {liveRunState}</p>
            <p className="mt-2">Runner: {data.runnerLabel}</p>
            <p className="mt-1">Current model: {data.requestedModel}</p>
            <p className="mt-1">Default run count: 3 for fast mode</p>
            <p className="mt-1">Cache behavior: cache disabled during replay to measure repeated executions</p>
            <p className="mt-1">Estimated token range: scenario-dependent; review preserved usage before launching repeated runs.</p>
            <p className="mt-2 text-ink-100">
              Repeated model runs may incur cost. Live GPT-backed replay never launches automatically from this page.
            </p>
          </div>
          {liveRunMessage ? (
            <div className="rounded-xl border border-signal-warning/35 bg-signal-warning/10 p-4 text-sm text-ink-100">
              {liveRunMessage}
            </div>
          ) : null}
          {liveRunState === "awaiting confirmation" ? (
            <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
              <p>Confirmation required before launching a GPT-backed replay.</p>
              <div className="mt-3 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void confirmLiveRun()}
                  className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
                >
                  Confirm live replay
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPendingRunKind(null);
                    setLiveRunState("ready");
                    setLiveRunMessage("Live replay was not launched.");
                  }}
                  className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => {
                if (!liveRunsEnabled) {
                  setLiveRunState("inconclusive");
                  setLiveRunMessage("Live replay is disabled. Preserved evidence remains available without additional API cost.");
                  return;
                }
                setPendingRunKind("individual");
                beginLiveRun();
              }}
              className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
            >
              Run selected individual replay
            </button>
            <button
              type="button"
              onClick={() => {
                if (!liveRunsEnabled) {
                  setLiveRunState("inconclusive");
                  setLiveRunMessage("Live replay is disabled. Preserved evidence remains available without additional API cost.");
                  return;
                }
                setPendingRunKind("pairwise");
                beginLiveRun();
              }}
              className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
            >
              Run selected pairwise replay
            </button>
          </div>
        </div>
      </SectionCard>

      <SectionCard id="artifact-linking" title="Artifact Linking" eyebrow="Evidence retrieval">
        <div className="flex flex-wrap gap-3">
          {data.scenarioLinks.map((item) => (
            <EvidenceLinkChip key={`${item.label}-${item.href ?? "missing"}`} item={item} />
          ))}
        </div>
      </SectionCard>
    </>
  );
}
