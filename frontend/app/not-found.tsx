import Link from "next/link";

import { EmptyState } from "@/components/empty-state";

export default function NotFoundPage() {
  return (
    <div className="space-y-6">
      <EmptyState
        title="Page not found"
        description="This route does not map to a saved Memory MRI view."
      />
      <div className="flex justify-center">
        <Link
          href="/"
          className="rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition hover:border-white/20 hover:bg-white/[0.04]"
        >
          Return to overview
        </Link>
      </div>
    </div>
  );
}
