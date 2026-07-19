import { notFound } from "next/navigation";

import { ScenarioDetailView } from "@/components/scenario-detail-view";
import { loadScenarioDetailEvidence } from "@/lib/server/scenario-detail-evidence";

export default async function BenchmarkScenarioPage({
  params,
  searchParams,
}: {
  params: Promise<{ scenarioId: string }>;
  searchParams: Promise<{ source?: string; trace?: string }>;
}) {
  const { scenarioId } = await params;
  const resolvedSearchParams = await searchParams;
  const data = await loadScenarioDetailEvidence(scenarioId, {
    source: resolvedSearchParams.source,
    traceId: resolvedSearchParams.trace,
  });

  if (!data) {
    notFound();
  }

  return <ScenarioDetailView data={data} showEvaluation />;
}
