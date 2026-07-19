import { z } from "zod";

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z
    .string()
    .url("NEXT_PUBLIC_API_BASE_URL must be a valid URL.")
    .min(1, "NEXT_PUBLIC_API_BASE_URL is required."),
  NEXT_PUBLIC_DEMO_MODE: z
    .enum(["true", "false"])
    .optional()
    .default("false"),
  NEXT_PUBLIC_ENABLE_LIVE_RUNS: z
    .enum(["true", "false"])
    .optional()
    .default("false"),
});

export class EnvironmentConfigError extends Error {
  issues: string[];

  constructor(issues: string[]) {
    super(issues.join(" "));
    this.name = "EnvironmentConfigError";
    this.issues = issues;
  }
}

export type PublicEnv = {
  apiBaseUrl: string;
  apiHost: string;
  demoMode: boolean;
  enableLiveRuns: boolean;
};

export function getPublicEnv(): PublicEnv {
  const parsed = publicEnvSchema.safeParse({
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_DEMO_MODE: process.env.NEXT_PUBLIC_DEMO_MODE,
    NEXT_PUBLIC_ENABLE_LIVE_RUNS: process.env.NEXT_PUBLIC_ENABLE_LIVE_RUNS,
  });

  if (!parsed.success) {
    throw new EnvironmentConfigError(parsed.error.issues.map((issue) => issue.message));
  }

  const apiBaseUrl = parsed.data.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/, "");

  return {
    apiBaseUrl,
    apiHost: new URL(apiBaseUrl).host,
    demoMode: parsed.data.NEXT_PUBLIC_DEMO_MODE === "true",
    enableLiveRuns: parsed.data.NEXT_PUBLIC_ENABLE_LIVE_RUNS === "true",
  };
}

export function getPublicEnvResult():
  | { ok: true; value: PublicEnv }
  | { ok: false; error: EnvironmentConfigError } {
  try {
    return { ok: true, value: getPublicEnv() };
  } catch (error) {
    if (error instanceof EnvironmentConfigError) {
      return { ok: false, error };
    }

    throw error;
  }
}
