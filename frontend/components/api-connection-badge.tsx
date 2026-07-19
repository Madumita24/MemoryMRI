"use client";

import { useHealthQuery } from "@/lib/api/hooks";

import { StatusBadge } from "./status-badge";

export function ApiConnectionBadge() {
  const healthQuery = useHealthQuery();

  if (healthQuery.isLoading) {
    return <StatusBadge label="checking" tone="info" />;
  }

  if (healthQuery.isError) {
    return <StatusBadge label="offline" tone="failure" />;
  }

  return <StatusBadge label="connected" tone="success" />;
}
