import { Suspense } from "react";

import { LoadingSkeleton } from "@/components/loading-skeleton";

import InvestigationsPageContent from "./page-content";

export default function InvestigationsPage() {
  return (
    <Suspense fallback={<LoadingSkeleton className="min-h-64" lines={8} />}>
      <InvestigationsPageContent />
    </Suspense>
  );
}
