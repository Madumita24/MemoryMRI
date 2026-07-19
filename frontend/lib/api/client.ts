import { z } from "zod";

import { EnvironmentConfigError, getPublicEnv } from "@/lib/env";

import { schemas } from "./schemas";

const DEFAULT_TIMEOUT_MS = 8000;

export class ApiClientError extends Error {
  status: number | null;
  code: string | null;
  kind: "api" | "network" | "validation" | "timeout" | "config";
  details?: unknown;

  constructor(
    message: string,
    options: {
      status?: number | null;
      code?: string | null;
      kind: "api" | "network" | "validation" | "timeout" | "config";
      details?: unknown;
    },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = options.status ?? null;
    this.code = options.code ?? null;
    this.kind = options.kind;
    this.details = options.details;
  }
}

type FetchMethod = "GET" | "POST";

type RequestOptions = {
  method?: FetchMethod;
  body?: unknown;
  timeoutMs?: number;
};

function buildUrl(path: string): string {
  const { apiBaseUrl } = getPublicEnv();
  return `${apiBaseUrl}${path}`;
}

function withTimeout(timeoutMs: number): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

async function parseJsonOrText(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

function parseApiError(
  payload: unknown,
  response: Response,
): ApiClientError {
  const parsed = schemas.apiError.safeParse(payload);

  if (parsed.success) {
    const detail =
      typeof parsed.data.detail === "string"
        ? parsed.data.detail
        : JSON.stringify(parsed.data.detail);

    return new ApiClientError(detail, {
      status: response.status,
      code: parsed.data.code ?? null,
      kind: "api",
      details: parsed.data.detail,
    });
  }

  return new ApiClientError(`Request failed with status ${response.status}.`, {
    status: response.status,
    code: null,
    kind: "api",
    details: payload,
  });
}

async function request<T>(
  path: string,
  schema: z.ZodSchema<T>,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";

  try {
    const response = await fetch(buildUrl(path), {
      method,
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: withTimeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS),
      cache: "no-store",
    });

    const payload = await parseJsonOrText(response);

    if (!response.ok) {
      throw parseApiError(payload, response);
    }

    const parsed = schema.safeParse(payload);

    if (!parsed.success) {
      throw new ApiClientError("API response validation failed.", {
        kind: "validation",
        details: parsed.error.flatten(),
      });
    }

    return parsed.data;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }

    if (error instanceof EnvironmentConfigError) {
      throw new ApiClientError(error.message, {
        kind: "config",
        details: error.issues,
      });
    }

    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiClientError("The backend request timed out.", {
        kind: "timeout",
      });
    }

    throw new ApiClientError("The backend is unavailable right now.", {
      kind: "network",
      details: error,
    });
  }
}

export const apiClient = {
  getHealth: () => request("/health", schemas.healthResponse),
  getDomains: () => request("/domains", z.array(schemas.domainInfo)),
  getScenarios: () => request("/scenarios", z.array(schemas.publicScenarioSummary)),
  getScenario: (scenarioId: string) =>
    request(`/scenarios/${scenarioId}`, schemas.publicScenarioDetail),
  getScenarioTraces: (scenarioId: string) =>
    request(`/scenarios/${scenarioId}/traces`, z.array(schemas.publicTrace)),
  getTrace: (traceId: string) => request(`/traces/${traceId}`, schemas.publicTrace),
  getInvestigation: (investigationId: string) =>
    request(`/investigations/${investigationId}`, schemas.publicInvestigation),
  getInvestigationResults: (investigationId: string) =>
    request(
      `/investigations/${investigationId}/results`,
      schemas.investigationResultsResponse,
    ),
  runIndividualReplay: (
    investigationId: string,
    body: {
      operation: "remove" | "disable" | "all";
      memory_id?: string;
    },
  ) =>
    request(
      `/investigations/${investigationId}/individual-replay`,
      schemas.publicInvestigation,
      {
        method: "POST",
        body,
      },
    ),
  runPairwiseReplay: (
    investigationId: string,
    body: {
      memory_a?: string;
      memory_b?: string;
      all_pairs?: boolean;
      shared_baseline_runs?: boolean;
      fresh_baseline_per_pair?: boolean;
    },
  ) =>
    request(
      `/investigations/${investigationId}/pairwise-replay`,
      z.unknown(),
      {
        method: "POST",
        body,
      },
    ),
  getProposal: (proposalId: string) =>
    request(`/proposals/${proposalId}`, schemas.repairProposal),
  getProposalDiff: (proposalId: string) =>
    request(`/proposals/${proposalId}/diff`, schemas.memoryDiff),
  getVerification: (verificationId: string) =>
    request(`/verifications/${verificationId}`, schemas.verificationRun),
  getArtifact: (artifactId: string) =>
    request(`/artifacts/${artifactId}`, schemas.verificationArtifact),
  getArtifactJson: (artifactId: string) =>
    request(`/artifacts/${artifactId}/json`, schemas.verificationArtifact),
  getArtifactMarkdown: (artifactId: string) =>
    request(`/artifacts/${artifactId}/markdown`, z.string()),
  runScenario: (body: { scenario_id: string; runner: "fake" | "openai" }) =>
    request("/runs", schemas.publicTrace, {
      method: "POST",
      body,
    }),
  createInvestigation: (body: {
    trace_id: string;
    mode?: "fast" | "deep" | "custom";
    run_count?: number;
  }) =>
    request("/investigations", schemas.publicInvestigation, {
      method: "POST",
      body,
    }),
  approveProposal: (proposalId: string, body: { reason: string; notes?: string }) =>
    request(`/proposals/${proposalId}/approve`, schemas.repairProposal, {
      method: "POST",
      body,
    }),
  rejectProposal: (proposalId: string, body: { reason: string; notes?: string }) =>
    request(`/proposals/${proposalId}/reject`, schemas.repairProposal, {
      method: "POST",
      body,
    }),
  applyProposal: (proposalId: string) =>
    request(`/proposals/${proposalId}/apply`, schemas.repairProposal, {
      method: "POST",
    }),
  revertProposal: (proposalId: string, body: { reason: string; notes?: string }) =>
    request(`/proposals/${proposalId}/revert`, schemas.repairProposal, {
      method: "POST",
      body,
    }),
  verifyOriginal: (body: { proposal_id: string; runner: "fake" | "openai" }) =>
    request("/verifications/original", schemas.verificationRun, {
      method: "POST",
      body,
    }),
  verifyDomain: (body: { proposal_id: string; runner: "fake" | "openai" }) =>
    request("/verifications/domain", schemas.verificationRun, {
      method: "POST",
      body,
    }),
  verifyFull: (body: { proposal_id: string; runner: "fake" | "openai" }) =>
    request("/verifications/full", schemas.verificationRun, {
      method: "POST",
      body,
    }),
  buildArtifact: (body: { proposal_id: string; verification_id?: string }) =>
    request("/artifacts", schemas.artifactSummary, {
      method: "POST",
      body,
    }),
  runBenchmark: (body: {
    runner?: "fake" | "openai";
    artifact_path?: string;
    summary_json_path?: string;
    summary_md_path?: string;
    traces_dir?: string;
  }) =>
    request("/benchmarks/run", schemas.benchmarkRunResponse, {
      method: "POST",
      body,
    }),
};

export const queryKeys = {
  artifact: (artifactId: string) => ["artifact", artifactId] as const,
  artifactMarkdown: (artifactId: string) => ["artifact-markdown", artifactId] as const,
  domains: ["domains"] as const,
  health: ["health"] as const,
  investigation: (investigationId: string) => ["investigation", investigationId] as const,
  investigationResults: (investigationId: string) =>
    ["investigation-results", investigationId] as const,
  proposal: (proposalId: string) => ["proposal", proposalId] as const,
  proposalDiff: (proposalId: string) => ["proposal-diff", proposalId] as const,
  scenario: (scenarioId: string) => ["scenario", scenarioId] as const,
  scenarioTraces: (scenarioId: string) => ["scenario-traces", scenarioId] as const,
  scenarios: ["scenarios"] as const,
  trace: (traceId: string) => ["trace", traceId] as const,
  verification: (verificationId: string) => ["verification", verificationId] as const,
};
