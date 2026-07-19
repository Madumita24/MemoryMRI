import { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string;
  detail?: string;
  accent?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface-900/72 p-5 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-ink-300">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-ink-50">{value}</p>
          {detail ? <p className="mt-2 text-sm text-ink-200">{detail}</p> : null}
        </div>
        {accent}
      </div>
    </div>
  );
}
