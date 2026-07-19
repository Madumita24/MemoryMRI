"use client";

import { EmptyState } from "@/components/empty-state";
import { ErrorPanel } from "@/components/error-panel";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { useDomainsQuery, useScenariosQuery } from "@/lib/api/hooks";

export default function BenchmarksPage() {
  const domainsQuery = useDomainsQuery();
  const scenariosQuery = useScenariosQuery();

  return (
    <>
      <PageHeader
        title="Benchmarks"
        description="Public benchmark catalog access is live. Full benchmark dashboards stay for the next milestone so we can keep the privacy boundary explicit."
      />

      <SectionCard title="Public benchmark catalog" eyebrow="Read-only">
        {domainsQuery.isLoading || scenariosQuery.isLoading ? <LoadingSkeleton lines={4} /> : null}
        {domainsQuery.isError ? (
          <ErrorPanel error={domainsQuery.error} retry={() => void domainsQuery.refetch()} />
        ) : null}
        {scenariosQuery.isError ? (
          <ErrorPanel error={scenariosQuery.error} retry={() => void scenariosQuery.refetch()} />
        ) : null}
        {!domainsQuery.isLoading && !scenariosQuery.isLoading && !domainsQuery.isError && !scenariosQuery.isError ? (
          <div className="space-y-3 text-sm text-ink-200">
            <p>
              The frontend can currently retrieve {scenariosQuery.data?.length ?? 0} public
              scenarios across {domainsQuery.data?.length ?? 0} domains without exposing
              benchmark-private answer keys.
            </p>
            <p>
              Later pages can layer expected-versus-actual benchmark views only where the backend
              explicitly provides evaluation artifacts.
            </p>
          </div>
        ) : null}
      </SectionCard>

      <EmptyState
        title="Benchmark dashboard intentionally deferred"
        description="This route is stable and connected, but the richer benchmark visualizations stay for Day 4B so we can keep the typed API layer and privacy rules settled first."
      />
    </>
  );
}
