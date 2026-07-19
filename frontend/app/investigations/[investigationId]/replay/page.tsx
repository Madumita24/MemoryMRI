import { notFound } from "next/navigation";

import { ReplayLaboratory } from "@/components/replay-laboratory";
import { loadReplayLabEvidence } from "@/lib/server/replay-lab-evidence";

export default async function InvestigationReplayPage({
  params,
  searchParams,
}: {
  params: Promise<{ investigationId: string }>;
  searchParams?: Promise<{ mode?: string }>;
}) {
  const { investigationId } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const data = await loadReplayLabEvidence(investigationId, {
    benchmarkMode: resolvedSearchParams.mode !== "agent",
  });

  if (!data) {
    notFound();
  }

  return <ReplayLaboratory data={data} />;
}
