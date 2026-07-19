import { ReactNode } from "react";

export function SectionCard({
  id,
  title,
  eyebrow,
  children,
}: {
  id?: string;
  title: string;
  eyebrow?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="rounded-xl border border-white/10 bg-surface-900/72 p-6 shadow-panel">
      {eyebrow ? (
        <p className="text-xs uppercase tracking-[0.22em] text-ink-300">{eyebrow}</p>
      ) : null}
      <h3 className="mt-1 text-xl font-semibold tracking-tight text-ink-50">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  );
}
