"use client";

import { useState } from "react";

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      className="rounded-md border border-white/10 px-2.5 py-1.5 text-xs text-ink-200 transition hover:bg-white/[0.05] hover:text-ink-50"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
