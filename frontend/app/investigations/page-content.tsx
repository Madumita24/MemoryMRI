"use client";

import { useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { ErrorPanel } from "@/components/error-panel";
import { IdentifierDisplay } from "@/components/identifier-display";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusBadge } from "@/components/status-badge";
import { Timestamp } from "@/components/timestamp";
import {
  useInvestigationQuery,
  useInvestigationResultsQuery,
} from "@/lib/api/hooks";

export default function InvestigationsPageContent() {
  const searchParams = useSearchParams();
  const investigationId = searchParams.get("id");
  const investigationQuery = useInvestigationQuery(investigationId);
  const resultsQuery = useInvestigationResultsQuery(investigationId);

  return (
    <>
      <PageHeader
        title="Investigations"
        description="Typed investigation retrieval is live. Add an investigation ID in the query string to inspect stored replay and evidence results."
      />

      {!investigationId ? (
        <EmptyState
          title="Choose an investigation"
          description="Open this route with ?id=INVESTIGATION_ID to load a real investigation and its evidence artifacts from the backend."
        />
      ) : null}

      {investigationId ? (
        <SectionCard title="Investigation summary" eyebrow="Live retrieval">
          {investigationQuery.isLoading || resultsQuery.isLoading ? <LoadingSkeleton lines={5} /> : null}
          {investigationQuery.isError ? (
            <ErrorPanel
              error={investigationQuery.error}
              retry={() => void investigationQuery.refetch()}
            />
          ) : null}
          {resultsQuery.isError ? (
            <ErrorPanel
              error={resultsQuery.error}
              retry={() => void resultsQuery.refetch()}
            />
          ) : null}
          {investigationQuery.data && resultsQuery.data ? (
            <div className="space-y-4">
              <IdentifierDisplay
                label="Investigation ID"
                value={investigationQuery.data.investigation_id}
              />
              <div className="flex flex-wrap gap-2">
                <StatusBadge label={investigationQuery.data.domain} tone="info" />
                <StatusBadge label={investigationQuery.data.mode} tone="replay" />
                <StatusBadge
                  label={`${investigationQuery.data.replay_results.length} replay result(s)`}
                  tone="semantic"
                />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    Original trace
                  </p>
                  <p className="mt-2 font-mono text-ink-50">
                    {investigationQuery.data.parent_trace_id}
                  </p>
                </div>
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    Created
                  </p>
                  <div className="mt-2">
                    <Timestamp value={investigationQuery.data.created_at} />
                  </div>
                </div>
              </div>
              <p className="text-sm text-ink-200">
                Optional evidence loaded: suspicion ranking{" "}
                {resultsQuery.data.suspicion_ranking ? "yes" : "no"}, contradictions{" "}
                {resultsQuery.data.contradictions ? "yes" : "no"}, pairwise replay{" "}
                {resultsQuery.data.pairwise_replay ? "yes" : "no"}.
              </p>
            </div>
          ) : null}
        </SectionCard>
      ) : null}
    </>
  );
}
