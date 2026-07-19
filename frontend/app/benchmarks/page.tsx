import { Suspense } from "react";

import { BenchmarkExplorer } from "@/components/benchmark-explorer";
import { loadBenchmarkExplorerEvidence } from "@/lib/server/benchmark-evidence";

export default async function BenchmarksPage() {
  const data = await loadBenchmarkExplorerEvidence();
  return (
    <Suspense fallback={null}>
      <BenchmarkExplorer data={data} />
    </Suspense>
  );
}
