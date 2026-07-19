import { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-white/12 bg-surface-900/60 p-8 text-center">
      <h3 className="text-lg font-semibold text-ink-50">{title}</h3>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-ink-200">{description}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
