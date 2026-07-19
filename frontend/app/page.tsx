import { OverviewDashboard } from "@/components/overview-dashboard";
import { loadDashboardEvidence } from "@/lib/server/benchmark-evidence";

export default async function OverviewPage() {
  const data = await loadDashboardEvidence();
  return <OverviewDashboard data={data} />;
}
