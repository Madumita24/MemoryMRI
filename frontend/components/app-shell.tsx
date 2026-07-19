"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { getPublicEnvResult } from "@/lib/env";
import { cn } from "@/lib/utils";

import { ApiConnectionBadge } from "./api-connection-badge";
import { StatusBadge } from "./status-badge";

const navigation = [
  { href: "/", label: "Overview" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/investigations", label: "Investigations" },
  { href: "/verification", label: "Verification" },
  { href: "/artifacts", label: "Artifacts" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const envResult = getPublicEnvResult();
  const env = envResult.ok
    ? envResult.value
    : {
        apiHost: "missing configuration",
        demoMode: false,
        enableLiveRuns: false,
      };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(117,169,255,0.14),_transparent_34%),linear-gradient(180deg,_#07111f_0%,_#0b1321_46%,_#08101b_100%)] text-ink-50">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-4 sm:px-6 lg:flex-row lg:px-8">
        <aside className="w-full rounded-xl border border-white/10 bg-surface-900/82 p-4 shadow-panel backdrop-blur lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)] lg:w-72">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-accent-blue">
              Memory MRI
            </p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">Diagnostic console</h1>
            <p className="mt-2 text-sm leading-6 text-ink-200">
              Debug and verify how persistent memories influence AI-agent behavior.
            </p>
          </div>

          <nav aria-label="Primary" className="space-y-1.5">
            {navigation.map((item) => {
              const active = pathname === item.href;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition-colors",
                    active
                      ? "border-accent-blue/60 bg-accent-blue/10 text-ink-50"
                      : "border-white/5 bg-white/[0.02] text-ink-200 hover:border-white/10 hover:bg-white/[0.04] hover:text-ink-50",
                  )}
                >
                  <span>{item.label}</span>
                  {active ? <span className="text-xs text-accent-blue">Live</span> : null}
                </Link>
              );
            })}
          </nav>

          <div className="mt-8 space-y-3 rounded-xl border border-white/6 bg-surface-950/60 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs uppercase tracking-[0.24em] text-ink-300">
                Backend
              </span>
              <ApiConnectionBadge />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                label={env.apiHost}
                tone={envResult.ok ? "info" : "failure"}
              />
              <StatusBadge
                label={env.enableLiveRuns ? "live runs enabled" : "live runs disabled"}
                tone={env.enableLiveRuns ? "warning" : "neutral"}
              />
              {env.demoMode ? <StatusBadge label="demo mode" tone="inconclusive" /> : null}
              {!envResult.ok ? (
                <StatusBadge label="env invalid" tone="failure" />
              ) : null}
            </div>
          </div>
        </aside>

        <div className="flex min-h-[70vh] flex-1 flex-col gap-6">{children}</div>
      </div>
    </div>
  );
}
