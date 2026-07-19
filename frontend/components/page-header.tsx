import { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-white/10 bg-surface-900/70 p-6 shadow-panel backdrop-blur sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-ink-300">
          Memory MRI
        </p>
        <h2 className="text-3xl font-semibold tracking-tight text-ink-50">{title}</h2>
        <p className="max-w-3xl text-sm leading-6 text-ink-200">{description}</p>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
