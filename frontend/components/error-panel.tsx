import { ReactNode } from "react";

import { ApiClientError } from "@/lib/api/client";

import { StatusBadge } from "./status-badge";

function describeError(error: ApiClientError): string {
  if (error.kind === "timeout") {
    return "The request timed out before the backend responded.";
  }

  if (error.kind === "network") {
    return "The frontend could not reach the backend service.";
  }

  if (error.kind === "validation") {
    return "The backend responded, but the payload did not match the expected public schema.";
  }

  if (error.kind === "config") {
    return "The frontend environment is missing required configuration.";
  }

  if (error.code === "non_applicable_repair_type") {
    return "The backend intentionally blocked a non-memory proposal from applying changes.";
  }

  return "The backend returned an API error.";
}

export function ErrorPanel({
  error,
  title = "Request failed",
  retry,
  footer,
}: {
  error: Error;
  title?: string;
  retry?: () => void;
  footer?: ReactNode;
}) {
  const apiError = error instanceof ApiClientError ? error : null;

  return (
    <div className="rounded-xl border border-signal-failure/30 bg-signal-failure/8 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold text-ink-50">{title}</h3>
        {apiError ? <StatusBadge label={apiError.kind} tone="failure" /> : null}
        {apiError?.status ? (
          <StatusBadge label={`HTTP ${apiError.status}`} tone="warning" />
        ) : null}
      </div>
      <p className="mt-3 text-sm leading-6 text-ink-100">{error.message}</p>
      {apiError ? <p className="mt-2 text-sm text-ink-200">{describeError(apiError)}</p> : null}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {retry ? (
          <button
            type="button"
            onClick={retry}
            className="rounded-lg border border-white/12 bg-white/[0.04] px-3 py-2 text-sm text-ink-50 transition hover:bg-white/[0.08]"
          >
            Retry
          </button>
        ) : null}
        {footer}
      </div>
    </div>
  );
}
