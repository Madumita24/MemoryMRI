import { EnvironmentConfigError, getPublicEnv } from "@/lib/env";

describe("getPublicEnv", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    process.env.NEXT_PUBLIC_DEMO_MODE = "false";
    process.env.NEXT_PUBLIC_ENABLE_LIVE_RUNS = "false";
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("parses the public environment", () => {
    const env = getPublicEnv();

    expect(env.apiBaseUrl).toBe("http://127.0.0.1:8000");
    expect(env.apiHost).toBe("127.0.0.1:8000");
    expect(env.demoMode).toBe(false);
    expect(env.enableLiveRuns).toBe(false);
  });

  it("throws a clear error when NEXT_PUBLIC_API_BASE_URL is missing", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    expect(() => getPublicEnv()).toThrow(EnvironmentConfigError);
    expect(() => getPublicEnv()).toThrow(/required/i);
  });
});
