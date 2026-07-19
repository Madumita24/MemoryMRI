import { Suspense } from "react";

import { LoadingSkeleton } from "@/components/loading-skeleton";

import VerificationPageContent from "./page-content";

export default function VerificationPage() {
  return (
    <Suspense fallback={<LoadingSkeleton className="min-h-64" lines={8} />}>
      <VerificationPageContent />
    </Suspense>
  );
}
