import { ErrorPanel } from "./error-panel";

export function BackendUnavailableScreen({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface-900/72 p-8 shadow-panel">
      <h2 className="text-2xl font-semibold tracking-tight text-ink-50">
        Backend unavailable
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-200">
        Memory MRI could not retrieve live backend data, so the frontend is staying in a
        transparent error state instead of showing a fake success.
      </p>
      <div className="mt-6">
        <ErrorPanel error={error} retry={retry} />
      </div>
    </div>
  );
}
