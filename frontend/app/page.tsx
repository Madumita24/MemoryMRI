"use client";

import { useMemo } from "react";

import { BackendUnavailableScreen } from "@/components/backend-unavailable-screen";
import { DomainBadge } from "@/components/domain-badge";
import { ErrorPanel } from "@/components/error-panel";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import { useDomainsQuery, useHealthQuery, useScenariosQuery } from "@/lib/api/hooks";
import { getPublicEnvResult } from "@/lib/env";
import { formatNumber } from "@/lib/utils";

export default function OverviewPage() {
  const envResult = getPublicEnvResult();
  const env = envResult.ok
    ? envResult.value
    : {
        apiHost: "missing configuration",
      };
  const healthQuery = useHealthQuery();
  const domainsQuery = useDomainsQuery();
  const scenariosQuery = useScenariosQuery();

  const retryAll = () => {
    void healthQuery.refetch();
    void domainsQuery.refetch();
    void scenariosQuery.refetch();
  };

  const lastRefresh = useMemo(() => {
    const timestamps = [
      healthQuery.dataUpdatedAt,
      domainsQuery.dataUpdatedAt,
      scenariosQuery.dataUpdatedAt,
    ].filter((value) => value > 0);

    if (!timestamps.length) {
      return null;
    }

    return new Date(Math.max(...timestamps)).toISOString();
  }, [domainsQuery.dataUpdatedAt, healthQuery.dataUpdatedAt, scenariosQuery.dataUpdatedAt]);

  if (healthQuery.isError) {
    return (
      <BackendUnavailableScreen
        error={healthQuery.error}
        retry={retryAll}
      />
    );
  }

  const loading = healthQuery.isLoading || domainsQuery.isLoading || scenariosQuery.isLoading;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Live backend visibility for health, public catalog counts, and the privacy-safe frontend boundary."
      />

      {!envResult.ok ? (
        <ErrorPanel
          title="Frontend configuration is incomplete"
          error={envResult.error}
        />
      ) : null}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <LoadingSkeleton lines={3} />
          <LoadingSkeleton lines={3} />
          <LoadingSkeleton lines={3} />
          <LoadingSkeleton lines={3} />
        </div>
      ) : null}

      {!loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Backend health"
            value={healthQuery.data?.status === "ok" ? "Healthy" : "Unknown"}
            detail="Pulled from GET /health"
            accent={<StatusBadge label="live" tone="success" />}
          />
          <MetricCard
            label="Domains detected"
            value={formatNumber(domainsQuery.data?.length ?? 0)}
            detail="Expected: 3 public domains"
          />
          <MetricCard
            label="Public scenarios"
            value={formatNumber(scenariosQuery.data?.length ?? 0)}
            detail="Expected: 30 retrievable scenarios"
          />
          <MetricCard
            label="API host"
            value={env.apiHost}
            detail={lastRefresh ? `Last refresh ${new Date(lastRefresh).toLocaleTimeString()}` : "No successful refresh yet"}
          />
        </div>
      ) : null}

      {domainsQuery.isError ? (
        <ErrorPanel
          title="Failed to load domains"
          error={domainsQuery.error}
          retry={() => void domainsQuery.refetch()}
        />
      ) : null}

      {scenariosQuery.isError ? (
        <ErrorPanel
          title="Failed to load public scenarios"
          error={scenariosQuery.error}
          retry={() => void scenariosQuery.refetch()}
        />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard title="Domain registry" eyebrow="Live catalog">
          <div className="grid gap-3 sm:grid-cols-3">
            {domainsQuery.data?.map((domain) => (
              <div
                key={domain.domain}
                className="rounded-lg border border-white/8 bg-surface-950/70 p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <DomainBadge domain={domain.domain} />
                  <span className="text-xs text-ink-300">
                    {domain.allowed_actions.length} actions
                  </span>
                </div>
                <ul className="mt-3 space-y-2 text-sm text-ink-200">
                  {domain.allowed_actions.map((action) => (
                    <li key={action} className="rounded-md bg-white/[0.03] px-2 py-1 font-mono text-xs">
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Frontend safety boundary" eyebrow="Privacy">
          <div className="space-y-4 text-sm leading-6 text-ink-200">
            <p>
              Normal scenario browsing is limited to the sanitized public API surface. The
              frontend does not reconstruct benchmark-only fields from other payloads.
            </p>
            <div className="flex flex-wrap gap-2">
              <StatusBadge label="expected_action hidden" tone="success" />
              <StatusBadge label="failure_category hidden" tone="success" />
              <StatusBadge label="benchmark hints hidden" tone="success" />
            </div>
            {lastRefresh ? (
              <div className="rounded-lg border border-white/8 bg-surface-950/70 px-3 py-2">
                <span className="text-xs uppercase tracking-[0.22em] text-ink-300">
                  Last successful refresh
                </span>
                <div className="mt-2">
                  <Timestamp value={lastRefresh} />
                </div>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    </>
  );
}
