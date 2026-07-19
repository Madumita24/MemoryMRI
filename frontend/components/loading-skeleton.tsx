export function LoadingSkeleton({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-white/8 bg-surface-900/55 p-5 ${className}`.trim()}
      aria-busy="true"
      data-testid="loading-skeleton"
    >
      <div className="animate-pulse space-y-3">
        {Array.from({ length: lines }).map((_, index) => (
          <div
            key={index}
            className="h-4 rounded bg-white/8"
            style={{ width: `${Math.max(35, 100 - index * 12)}%` }}
          />
        ))}
      </div>
    </div>
  );
}
