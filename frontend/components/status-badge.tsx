import { cn } from "@/lib/utils";

type StatusTone =
  | "success"
  | "failure"
  | "warning"
  | "inconclusive"
  | "info"
  | "concern"
  | "replay"
  | "semantic"
  | "neutral";

const toneStyles: Record<StatusTone, string> = {
  success: "border-signal-success/35 bg-signal-success/12 text-signal-success",
  failure: "border-signal-failure/35 bg-signal-failure/12 text-signal-failure",
  warning: "border-signal-warning/35 bg-signal-warning/12 text-signal-warning",
  inconclusive: "border-signal-inconclusive/35 bg-signal-inconclusive/12 text-signal-inconclusive",
  info: "border-signal-info/35 bg-signal-info/12 text-signal-info",
  concern: "border-signal-concern/35 bg-signal-concern/12 text-signal-concern",
  replay: "border-signal-replay/35 bg-signal-replay/12 text-signal-replay",
  semantic: "border-signal-semantic/35 bg-signal-semantic/12 text-signal-semantic",
  neutral: "border-white/12 bg-white/[0.04] text-ink-200",
};

export function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: StatusTone;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium tracking-wide",
        toneStyles[tone],
      )}
    >
      {label}
    </span>
  );
}
