"use client";

import Link from "next/link";

import { DomainBadge } from "@/components/domain-badge";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import { getDomainLabel, type DashboardEvidence } from "@/lib/benchmark-shared";
import { formatNumber } from "@/lib/utils";

function verdictTone(value: string | null) {
  if (!value) {
    return "neutral" as const;
  }

  if (value.includes("VERIFIED")) {
    return "success" as const;
  }

  if (value.includes("NOT_APPLICABLE")) {
    return "warning" as const;
  }

  if (value.includes("INCONCLUSIVE")) {
    return "inconclusive" as const;
  }

  return "concern" as const;
}

export function OverviewDashboard({ data }: { data: DashboardEvidence }) {
  const gpt = data.gptBaseline;
  const fake = data.fakeBaseline;

  return (
    <>
      <PageHeader title={data.title} description={data.description} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Official GPT baseline"
          value={`${gpt.overall.passed}/${gpt.overall.attempted}`}
          detail={`${gpt.runnerType} • ${gpt.model} • ${gpt.promptVersion}`}
          accent={<StatusBadge label="official frozen run" tone="success" />}
        />
        <MetricCard
          label="Deterministic test baseline"
          value={`${fake.overall.passed}/${fake.overall.attempted}`}
          detail={`${fake.runnerType} • ${fake.promptVersion}`}
          accent={<StatusBadge label="repeatable regression runner" tone="info" />}
        />
        <MetricCard
          label="Failed GPT scenarios"
          value={formatNumber(gpt.overall.failed)}
          detail="cs_01 and exp_09 remain the only official GPT failures."
        />
        <MetricCard
          label="Infrastructure errors"
          value={formatNumber(gpt.overall.infrastructureErrors)}
          detail="Official GPT baseline recorded zero infrastructure failures."
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Investigations"
          value={formatNumber(data.counts.investigations)}
          detail="Persisted Day 3 investigations"
        />
        <MetricCard
          label="Proposals"
          value={formatNumber(data.counts.proposals)}
          detail="Evidence-gated repair proposals"
        />
        <MetricCard
          label="Verification artifacts"
          value={formatNumber(data.counts.verificationArtifacts)}
          detail="Stored audit artifacts"
        />
        <MetricCard
          label="New regressions"
          value={formatNumber(data.counts.newRegressions)}
          detail="Across reviewed verification outcomes"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {data.domainCards.map((domain) => (
          <SectionCard
            key={domain.domain}
            title={domain.label}
            eyebrow="Domain status"
          >
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <DomainBadge domain={domain.domain} />
                <StatusBadge
                  label={domain.statusLabel}
                  tone={domain.gptFailureCount === 0 ? "success" : "warning"}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-3">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">GPT result</p>
                  <p className="mt-2 text-2xl font-semibold text-ink-50">
                    {domain.gptPassCount}/{domain.scenarioCount}
                  </p>
                </div>
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-3">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Investigations</p>
                  <p className="mt-2 text-2xl font-semibold text-ink-50">
                    {domain.investigationCount}
                  </p>
                </div>
              </div>
              <p className="text-sm text-ink-200">
                {domain.gptFailureCount} GPT failures across {domain.scenarioCount} scenarios.
              </p>
              <Link
                href={`/benchmarks?source=gpt&domain=${domain.domain}`}
                className="inline-flex rounded-full border border-white/10 px-3 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
              >
                View filtered benchmark
              </Link>
            </div>
          </SectionCard>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard title="Failure Overview" eyebrow="Evaluation-only view">
          <div className="space-y-4">
            {data.failureCards.map((card) => (
              <div
                key={card.scenarioId}
                className="rounded-xl border border-white/8 bg-surface-950/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-ink-50">{card.scenarioId}</span>
                      <DomainBadge domain={card.domain} />
                    </div>
                    <p className="mt-2 text-sm text-ink-200">
                      Expected action: <span className="font-mono text-ink-100">{card.expectedAction}</span>
                    </p>
                    <p className="mt-1 text-sm text-ink-200">
                      Original GPT action: <span className="font-mono text-ink-100">{card.actualAction}</span>
                    </p>
                  </div>
                  <StatusBadge
                    label={card.verificationVerdict ?? "not verified"}
                    tone={verdictTone(card.verificationVerdict)}
                  />
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                    <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Investigation</p>
                    <p className="mt-2 text-sm text-ink-100">
                      {card.investigationId ?? "No investigation record"}
                    </p>
                    <p className="mt-1 text-sm text-ink-200">{card.investigationStatus}</p>
                  </div>
                  <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                    <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Memory dependence</p>
                    <p className="mt-2 text-sm text-ink-100">
                      {card.memoryDependenceClassification ?? "not classified"}
                    </p>
                  </div>
                </div>
                <p className="mt-4 text-sm leading-6 text-ink-200">{card.replaySummary}</p>
              </div>
            ))}
          </div>
        </SectionCard>

        <div className="space-y-4">
          <SectionCard title="Recent Investigations" eyebrow="Preserved evidence">
            <div className="space-y-3">
              {data.recentInvestigations.map((item) => (
                <Link
                  key={item.investigationId}
                  href={`/investigations?investigationId=${item.investigationId}`}
                  className="block rounded-lg border border-white/8 bg-surface-950/70 p-3 transition hover:border-white/16 hover:bg-white/[0.04]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-sm text-ink-50">{item.scenarioId}</span>
                    <StatusBadge label={item.verdict} tone={verdictTone(item.verdict)} />
                  </div>
                  <p className="mt-2 text-sm text-ink-200">{getDomainLabel(item.domain)}</p>
                  <p className="mt-1 text-sm text-ink-200">{item.evidenceSummary}</p>
                  <p className="mt-1 text-xs text-ink-300">{item.latestProposal}</p>
                </Link>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Recent Activity" eyebrow="Frozen Day 3 snapshot">
            <div className="space-y-3">
              {data.recentActivity.map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-white/8 bg-surface-950/70 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <StatusBadge label={item.type} tone="neutral" />
                    <span className="font-mono text-xs text-ink-300">{item.id}</span>
                  </div>
                  <p className="mt-2 text-sm text-ink-100">{item.label}</p>
                  <p className="mt-1 text-sm text-ink-200 break-all">{item.detail}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">Snapshot timestamp</p>
              <div className="mt-2 text-sm text-ink-100">
                <Timestamp value={data.frozenSnapshotTimestamp} />
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </>
  );
}
