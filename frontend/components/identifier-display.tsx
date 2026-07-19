import { ReactNode } from "react";

import { CopyButton } from "./copy-button";

export function IdentifierDisplay({
  label,
  value,
  trailing,
}: {
  label: string;
  value: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/8 bg-surface-950/70 px-3 py-2">
      <span className="text-xs uppercase tracking-[0.22em] text-ink-300">{label}</span>
      <code className="font-mono text-sm text-ink-50">{value}</code>
      <CopyButton value={value} />
      {trailing}
    </div>
  );
}
