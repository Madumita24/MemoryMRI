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
import { useVerificationQuery } from "@/lib/api/hooks";

export default function VerificationPageContent() {
  const searchParams = useSearchParams();
  const verificationId = searchParams.get("id");
  const verificationQuery = useVerificationQuery(verificationId);

  return (
    <>
      <PageHeader
        title="Verification"
        description="Verification retrieval is wired for original-case, domain, and full-benchmark evidence without exposing public scenario pages to benchmark answer keys."
      />

      {!verificationId ? (
        <EmptyState
          title="Choose a verification run"
          description="Open this route with ?id=VERIFICATION_ID to inspect a persisted verification result."
        />
      ) : null}

      {verificationId ? (
        <SectionCard title="Verification result" eyebrow="Live retrieval">
          {verificationQuery.isLoading ? <LoadingSkeleton lines={5} /> : null}
          {verificationQuery.isError ? (
            <ErrorPanel
              error={verificationQuery.error}
              retry={() => void verificationQuery.refetch()}
            />
          ) : null}
          {verificationQuery.data ? (
            <div className="space-y-4">
              <IdentifierDisplay label="Verification ID" value={verificationQuery.data.verification_id} />
              <div className="flex flex-wrap gap-2">
                <StatusBadge label={verificationQuery.data.verdict} tone="inconclusive" />
                <StatusBadge label={verificationQuery.data.domain} tone="info" />
                <StatusBadge label={verificationQuery.data.model} tone="semantic" />
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    Repaired failures
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-ink-50">
                    {verificationQuery.data.repaired_failures.length}
                  </p>
                </div>
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    Persistent failures
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-ink-50">
                    {verificationQuery.data.persistent_failures.length}
                  </p>
                </div>
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    New regressions
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-ink-50">
                    {verificationQuery.data.new_regressions.length}
                  </p>
                </div>
              </div>
              <Timestamp value={verificationQuery.data.created_at} />
            </div>
          ) : null}
        </SectionCard>
      ) : null}
    </>
  );
}
