import Link from "next/link";

import { DomainBadge } from "@/components/domain-badge";
import { EvidenceTypeBadge } from "@/components/evidence-type-badge";
import { IdentifierDisplay } from "@/components/identifier-display";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import type {
  ScenarioDetailEvidence,
  ScenarioEvidenceLink,
  ScenarioMemoryView,
  ScenarioTraceView,
} from "@/lib/benchmark-shared";
import { getDomainLabel, toSentenceCase } from "@/lib/benchmark-shared";

function toneForMemoryStatus(status: string) {
  switch (status) {
    case "active":
      return "success" as const;
    case "stale":
      return "warning" as const;
    case "superseded":
      return "info" as const;
    case "uncertain":
      return "inconclusive" as const;
    case "invalid":
      return "failure" as const;
    default:
      return "neutral" as const;
  }
}

function toneForTrace(trace: ScenarioTraceView) {
  if (trace.error) {
    return "failure" as const;
  }

  if (trace.passed === true) {
    return "success" as const;
  }

  if (trace.passed === false) {
    return "warning" as const;
  }

  return "neutral" as const;
}

function JsonBlock({ value }: { value: Record<string, unknown> }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-white/8 bg-surface-950/80 p-4 text-xs leading-6 text-ink-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function EvidenceLinkChip({ item }: { item: ScenarioEvidenceLink }) {
  if (!item.href) {
    return (
      <span className="inline-flex rounded-full border border-white/8 px-3 py-2 text-sm text-ink-400">
        {item.label} unavailable
      </span>
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

function MemoryCard({ memory }: { memory: ScenarioMemoryView }) {
  return (
    <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-ink-50">{memory.memoryId}</span>
            <StatusBadge label={memory.status} tone={toneForMemoryStatus(memory.status)} />
            {memory.analysisFlags.map((flag) => (
              <StatusBadge key={flag} label={flag} tone="concern" />
            ))}
          </div>
          <p className="text-sm text-ink-200">{memory.content}</p>
        </div>
        <div className="text-right text-xs text-ink-300">
          <p>priority {memory.retrievalPriority}</p>
          <p>confidence {memory.confidence.toFixed(2)}</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Source</p>
          <p className="mt-2">{memory.source}</p>
          <p className="mt-1 font-mono text-xs text-ink-300">{memory.entityId}</p>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Created</p>
          <div className="mt-2">
            <Timestamp value={memory.createdAt} />
          </div>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Validity</p>
          <p className="mt-2">From: {memory.validFrom ? new Date(memory.validFrom).toLocaleString() : "n/a"}</p>
          <p className="mt-1">Until: {memory.validUntil ? new Date(memory.validUntil).toLocaleString() : "open"}</p>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Superseding</p>
          <p className="mt-2 font-mono text-xs text-ink-100">
            {memory.supersedes.length ? memory.supersedes.join(", ") : "none"}
          </p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[0.7fr_1.3fr]">
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3 text-sm text-ink-200">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Tags</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {memory.tags.map((tag) => (
              <StatusBadge key={tag} label={tag} tone="neutral" />
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Operational metadata</p>
          <div className="mt-2">
            <JsonBlock value={memory.operationalMetadata} />
          </div>
        </div>
      </div>
    </div>
  );
}

function TraceSwitcher({
  data,
  selectedTrace,
}: {
  data: ScenarioDetailEvidence;
  selectedTrace: ScenarioTraceView | null;
}) {
  return (
    <SectionCard title="Trace Selection" eyebrow="Chronological traces">
      <div className="space-y-3">
        {data.traces.map((trace) => {
          const isSelected = trace.traceId === selectedTrace?.traceId;
          const href = `/benchmarks/${data.scenarioId}?source=${data.selectedSource}&trace=${trace.traceId}`;
          return (
            <Link
              key={trace.traceId}
              href={href}
              className={`block rounded-xl border p-4 transition ${
                isSelected
                  ? "border-signal-info/45 bg-signal-info/10"
                  : "border-white/8 bg-surface-950/70 hover:border-white/16 hover:bg-white/[0.04]"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge label={trace.kindLabel} tone={trace.officialBaseline ? "success" : "info"} />
                    <StatusBadge label={trace.runnerLabel} tone={trace.runnerLabel === "GPT-5.6" ? "semantic" : "replay"} />
                    {trace.error ? (
                      <StatusBadge label="infrastructure error" tone="failure" />
                    ) : (
                      <StatusBadge
                        label={trace.passed === true ? "pass" : trace.passed === false ? "fail" : "not evaluated"}
                        tone={toneForTrace(trace)}
                      />
                    )}
                  </div>
                  <p className="font-mono text-sm text-ink-100">{trace.traceId}</p>
                  <p className="text-sm text-ink-200">{trace.sourceLabel}</p>
                </div>
                <div className="text-sm text-ink-200">
                  <Timestamp value={trace.createdAt} />
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </SectionCard>
  );
}

export function ScenarioDetailView({
  data,
  showEvaluation = true,
}: {
  data: ScenarioDetailEvidence;
  showEvaluation?: boolean;
}) {
  const trace = data.selectedTrace;

  return (
    <>
      <PageHeader
        title={data.title}
        description={`Trace detail for ${data.scenarioId} in ${getDomainLabel(data.domain)}.`}
      />

      <SectionCard title="Scenario Header" eyebrow="Benchmark execution">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg text-ink-50">{data.scenarioId}</span>
            <DomainBadge domain={data.domain} />
            <StatusBadge label={data.selectedRunnerLabel} tone="semantic" />
            <StatusBadge label={data.investigationStatus} tone={data.investigationStatus === "investigated" ? "info" : "neutral"} />
            {data.verificationVerdict ? (
              <StatusBadge label={data.verificationVerdict} tone="inconclusive" />
            ) : null}
            {showEvaluation && data.benchmarkEvaluation.passed !== null ? (
              <StatusBadge
                label={data.benchmarkEvaluation.passed ? "benchmark pass" : "benchmark fail"}
                tone={data.benchmarkEvaluation.passed ? "success" : "warning"}
              />
            ) : null}
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <IdentifierDisplay label="Scenario ID" value={data.scenarioId} />
            <div className="rounded-lg border border-white/8 bg-surface-950/70 px-3 py-2 text-sm text-ink-200">
              <span className="text-xs uppercase tracking-[0.22em] text-ink-300">Domain</span>
              <p className="mt-2">{getDomainLabel(data.domain)}</p>
            </div>
            <div className="rounded-lg border border-white/8 bg-surface-950/70 px-3 py-2 text-sm text-ink-200">
              <span className="text-xs uppercase tracking-[0.22em] text-ink-300">Latest trace</span>
              <div className="mt-2">
                {data.latestTraceTimestamp ? <Timestamp value={data.latestTraceTimestamp} /> : "No stored trace"}
              </div>
            </div>
            <div className="rounded-lg border border-white/8 bg-surface-950/70 px-3 py-2 text-sm text-ink-200">
              <span className="text-xs uppercase tracking-[0.22em] text-ink-300">Selected trace</span>
              <p className="mt-2 font-mono text-xs text-ink-100">{trace?.traceId ?? "No trace selected"}</p>
            </div>
          </div>
          {showEvaluation ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Expected action</p>
                <p className="mt-2 font-mono text-sm text-ink-100">{data.benchmarkEvaluation.expectedAction ?? "n/a"}</p>
              </div>
              <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Actual action</p>
                <p className="mt-2 font-mono text-sm text-ink-100">{data.benchmarkEvaluation.actualAction ?? "n/a"}</p>
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>

      {data.traceNotice ? (
        <SectionCard title="Trace Availability" eyebrow="Stored evidence limitation">
          <p className="text-sm leading-6 text-ink-200">{data.traceNotice}</p>
        </SectionCard>
      ) : null}

      <TraceSwitcher data={data} selectedTrace={trace} />

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <SectionCard title="Agent Input" eyebrow="User request">
          <div className="space-y-4">
            <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Exact user request</p>
              <p className="mt-3 text-sm leading-6 text-ink-100">{trace?.userInput ?? "No user input stored."}</p>
            </div>
            <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Agent-visible snapshot</p>
              <p className="mt-2 text-sm text-ink-200">
                {trace ? `${trace.memories.length} memories serialized for the runner.` : "No snapshot available."}
              </p>
              {trace ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusBadge label={trace.runnerLabel} tone="semantic" />
                  <StatusBadge label={`schema ${trace.agentInputSchemaVersion ?? "unknown"}`} tone="info" />
                  <StatusBadge label={`${trace.retrievedMemoryIds.length} retrieved memory IDs`} tone="replay" />
                </div>
              ) : null}
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Benchmark Evaluation Information" eyebrow="Evaluation-only">
          <div className="space-y-4">
            <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Benchmark source</p>
              <p className="mt-2">{data.benchmarkEvaluation.benchmarkVersion}</p>
              <p className="mt-1">{data.benchmarkEvaluation.runnerType}</p>
              <p className="mt-1">{data.benchmarkEvaluation.evaluatorName}</p>
            </div>
            <div className={`grid gap-3 ${showEvaluation ? "md:grid-cols-2" : ""}`}>
              {showEvaluation ? (
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Expected action</p>
                  <p className="mt-2 font-mono text-sm text-ink-100">
                    {data.benchmarkEvaluation.expectedAction ?? "n/a"}
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  Agent-visible mode is active. Expected-action benchmark labels stay hidden on this view.
                </div>
              )}
              <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Actual action</p>
                <p className="mt-2 font-mono text-sm text-ink-100">{data.benchmarkEvaluation.actualAction ?? "n/a"}</p>
              </div>
            </div>
            {data.benchmarkEvaluation.infrastructureError ? (
              <div className="rounded-xl border border-signal-failure/35 bg-signal-failure/10 p-4 text-sm text-ink-100">
                <p className="text-xs uppercase tracking-[0.22em] text-signal-failure">Infrastructure error</p>
                <p className="mt-2">{data.benchmarkEvaluation.infrastructureError}</p>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                <StatusBadge
                  label={data.benchmarkEvaluation.passed ? "evaluated pass" : "evaluated failure"}
                  tone={data.benchmarkEvaluation.passed ? "success" : "warning"}
                />
                {data.benchmarkEvaluation.failureCategory ? (
                  <StatusBadge label={toSentenceCase(data.benchmarkEvaluation.failureCategory)} tone="neutral" />
                ) : null}
              </div>
            )}
            {data.deterministicComparison ? (
              <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Deterministic comparison</p>
                <p className="mt-2">
                  {data.deterministicComparison.runnerType}: {data.deterministicComparison.actualAction} vs expected {data.deterministicComparison.expectedAction}
                </p>
                <p className="mt-1">{data.deterministicComparison.benchmarkVersion}</p>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Execution Timeline" eyebrow="Observable steps">
        {trace ? (
          <div className="space-y-4">
            {trace.timeline.map((step, index) => (
              <div key={step.id} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className="mt-1 h-3 w-3 rounded-full bg-signal-info" />
                  {index < trace.timeline.length - 1 ? <div className="mt-2 h-full w-px bg-white/10" /> : null}
                </div>
                <div className="flex-1 rounded-xl border border-white/8 bg-surface-950/70 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold text-ink-50">{step.label}</h4>
                      <StatusBadge
                        label={step.status}
                        tone={
                          step.status === "complete"
                            ? "success"
                            : step.status === "warning"
                              ? "warning"
                              : step.status === "error"
                                ? "failure"
                                : "neutral"
                        }
                      />
                      <EvidenceTypeBadge label={step.evidenceType} type={step.evidenceType} />
                    </div>
                    <span className="text-xs text-ink-300">
                      {step.timestamp ? <Timestamp value={step.timestamp} /> : "timestamp unavailable"}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-ink-200">{step.detail}</p>
                  {step.traceId ? (
                    <p className="mt-2 font-mono text-xs text-ink-300">{step.traceId}</p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">No stored trace timeline is available for this scenario.</p>
        )}
      </SectionCard>

      <SectionCard title="Memories Retrieved" eyebrow="Agent-visible memory snapshot">
        {trace ? (
          <div className="space-y-4">
            {trace.memories.map((memory) => (
              <MemoryCard key={memory.memoryId} memory={memory} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-200">No agent-visible memories were stored for the selected trace.</p>
        )}
      </SectionCard>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <SectionCard title="Agent Response" eyebrow="Observable structured output">
          {trace ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Selected action</p>
                  <p className="mt-2 font-mono text-sm text-ink-100">{trace.selectedAction ?? "none"}</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Cited memories</p>
                  <p className="mt-2 font-mono text-xs text-ink-100">
                    {trace.citedMemoryIds.length ? trace.citedMemoryIds.join(", ") : "none"}
                  </p>
                </div>
              </div>
              <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Concise rationale</p>
                <p className="mt-2 leading-6 text-ink-100">{trace.conciseRationale ?? "No rationale stored."}</p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Uncertainty</p>
                  <p className="mt-2 text-sm text-ink-100">{trace.uncertainty ?? "n/a"}</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Needs human review</p>
                  <p className="mt-2 text-sm text-ink-100">{String(trace.needsHumanReview ?? false)}</p>
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Action arguments</p>
                <div className="mt-2">
                  <JsonBlock value={trace.actionArguments} />
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-200">No structured response is available for the selected trace.</p>
          )}
        </SectionCard>

        <SectionCard title="Trace Metadata" eyebrow="Stored identifiers and costs">
          {trace ? (
            <div className="space-y-4">
              <IdentifierDisplay label="Trace ID" value={trace.traceId} />
              <IdentifierDisplay label="Run ID" value={trace.runId} />
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Models</p>
                  <p className="mt-2">Requested: {trace.requestedModel}</p>
                  <p className="mt-1">Returned: {trace.responseModel}</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Prompt</p>
                  <p className="mt-2">Version: {trace.promptVersion}</p>
                  <p className="mt-1 font-mono text-xs text-ink-300 break-all">{trace.promptContentHash ?? "hash unavailable"}</p>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Request hash</p>
                  <p className="mt-2 font-mono text-xs text-ink-100 break-all">{trace.requestHash ?? "not stored"}</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Git commit</p>
                  <p className="mt-2 font-mono text-xs text-ink-100 break-all">{trace.gitCommitHash ?? "not available for this trace"}</p>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Latency</p>
                  <p className="mt-2">{trace.latencyMs} ms</p>
                  <p className="mt-1">Cache lookup: {trace.cacheLookupLatencyMs ?? "n/a"} ms</p>
                  <p className="mt-1">Original model: {trace.originalModelLatencyMs ?? "n/a"} ms</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Cache</p>
                  <p className="mt-2">{trace.cacheEnabled ? "enabled" : "disabled"}</p>
                  <p className="mt-1">{trace.cacheHit ? "hit" : "miss"}</p>
                  <p className="mt-1">Billable API call: {String(trace.billableApiCall)}</p>
                </div>
                <div className="rounded-xl border border-white/8 bg-white/[0.03] p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Token usage</p>
                  <p className="mt-2">Input: {trace.requestTokenUsage?.input_tokens ?? trace.tokenUsage.input_tokens ?? 0}</p>
                  <p className="mt-1">Output: {trace.requestTokenUsage?.output_tokens ?? trace.tokenUsage.output_tokens ?? 0}</p>
                  <p className="mt-1">Total: {trace.requestTokenUsage?.total_tokens ?? trace.tokenUsage.total_tokens ?? 0}</p>
                </div>
              </div>
              {trace.error ? (
                <div className="rounded-xl border border-signal-failure/35 bg-signal-failure/10 p-4 text-sm text-ink-100">
                  <p className="text-xs uppercase tracking-[0.22em] text-signal-failure">Infrastructure error</p>
                  <p className="mt-2">{trace.error.message ?? "Unknown infrastructure error."}</p>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-ink-200">No trace metadata is available.</p>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Evidence Navigation" eyebrow="Related investigation and verification">
        <div className="flex flex-wrap gap-3">
          {data.evidenceLinks.map((item) => (
            <EvidenceLinkChip key={item.label} item={item} />
          ))}
        </div>
      </SectionCard>
    </>
  );
}
