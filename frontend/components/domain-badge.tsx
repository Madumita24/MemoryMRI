import { DomainInfo } from "@/lib/api/schemas";

import { StatusBadge } from "./status-badge";

const toneByDomain: Record<DomainInfo["domain"], Parameters<typeof StatusBadge>[0]["tone"]> = {
  customer_support: "info",
  devops: "replay",
  workplace_expense: "warning",
};

export function DomainBadge({ domain }: { domain: DomainInfo["domain"] }) {
  return <StatusBadge label={domain.replaceAll("_", " ")} tone={toneByDomain[domain]} />;
}
