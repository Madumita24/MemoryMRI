import { Suspense } from "react";

import { LoadingSkeleton } from "@/components/loading-skeleton";

import ArtifactsPageContent from "./page-content";

export default function ArtifactsPage() {
  return (
    <Suspense fallback={<LoadingSkeleton className="min-h-64" lines={8} />}>
      <ArtifactsPageContent />
    </Suspense>
  );
}
