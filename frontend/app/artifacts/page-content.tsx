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
  useArtifactMarkdownQuery,
  useArtifactQuery,
} from "@/lib/api/hooks";

export default function ArtifactsPageContent() {
  const searchParams = useSearchParams();
  const artifactId = searchParams.get("id");
  const artifactQuery = useArtifactQuery(artifactId);
  const markdownQuery = useArtifactMarkdownQuery(artifactId);

  return (
    <>
      <PageHeader
        title="Artifacts"
        description="Verification artifacts can be retrieved as structured JSON or Markdown. The UI stays read-only for this milestone."
      />

      {!artifactId ? (
        <EmptyState
          title="Choose an artifact"
          description="Open this route with ?id=ARTIFACT_ID to inspect a stored verification artifact and its Markdown export."
        />
      ) : null}

      {artifactId ? (
        <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <SectionCard title="Artifact metadata" eyebrow="JSON">
            {artifactQuery.isLoading ? <LoadingSkeleton lines={5} /> : null}
            {artifactQuery.isError ? (
              <ErrorPanel error={artifactQuery.error} retry={() => void artifactQuery.refetch()} />
            ) : null}
            {artifactQuery.data ? (
              <div className="space-y-4">
                <IdentifierDisplay label="Artifact ID" value={artifactQuery.data.artifact_id} />
                <IdentifierDisplay
                  label="Fingerprint"
                  value={artifactQuery.data.content_hash}
                />
                <div className="flex flex-wrap gap-2">
                  <StatusBadge label={artifactQuery.data.verification_verdict} tone="inconclusive" />
                  <StatusBadge label={artifactQuery.data.domain} tone="info" />
                </div>
                <div className="rounded-lg border border-white/8 bg-surface-950/70 p-4 text-sm text-ink-200">
                  <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                    Likely influential memories
                  </p>
                  <ul className="mt-3 space-y-2 font-mono text-xs text-ink-100">
                    {artifactQuery.data.likely_influential_memories.map((memoryId) => (
                      <li key={memoryId}>{memoryId}</li>
                    ))}
                  </ul>
                </div>
                <Timestamp value={artifactQuery.data.created_at} />
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Markdown export" eyebrow="Readable">
            {markdownQuery.isLoading ? <LoadingSkeleton lines={10} /> : null}
            {markdownQuery.isError ? (
              <ErrorPanel error={markdownQuery.error} retry={() => void markdownQuery.refetch()} />
            ) : null}
            {markdownQuery.data ? (
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-white/8 bg-surface-950/80 p-4 text-sm leading-6 text-ink-100">
                {markdownQuery.data}
              </pre>
            ) : null}
          </SectionCard>
        </div>
      ) : null}
    </>
  );
}
