import { StatusBadge } from "./status-badge";

const evidenceToneMap = {
  contradiction: "concern",
  replay: "replay",
  semantic: "semantic",
  support: "info",
} as const;

export function EvidenceTypeBadge({
  label,
  type,
}: {
  label: string;
  type: keyof typeof evidenceToneMap;
}) {
  return <StatusBadge label={label} tone={evidenceToneMap[type]} />;
}
