import { ApiClientError, apiClient } from "@/lib/api/client";

describe("apiClient", () => {
  const originalEnv = process.env;
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "false",
    };
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("parses successful health responses", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiClient.getHealth()).resolves.toEqual({ status: "ok" });
  });

  it("parses API errors with codes", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "This proposal type must not modify memory or create a version.",
          code: "non_applicable_repair_type",
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(apiClient.getArtifact("bad-id")).rejects.toMatchObject({
      kind: "api",
      status: 400,
      code: "non_applicable_repair_type",
    });
  });

  it("rejects public scenario payloads that contain benchmark-private fields", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          scenario_id: "cs_01",
          title: "Customer support example",
          domain: "customer_support",
          user_input: "Help with a refund",
          allowed_actions: ["ISSUE_REFUND"],
          memory_ids: ["cs_01_mem_1"],
          expected_action: "ISSUE_REFUND",
          agent_input: {
            schema_version: "day2a-v1",
            scenario_id: "cs_01",
            domain: "customer_support",
            user_input: "Help with a refund",
            allowed_actions: ["ISSUE_REFUND"],
            memories: [
              {
                memory_id: "cs_01_mem_1",
                entity_id: "customer_1",
                content: "Refund policy",
                source: "policy",
                created_at: "2026-07-18T00:00:00Z",
                valid_from: null,
                valid_until: null,
                status: "active",
                confidence: 1,
                retrieval_priority: 90,
                supersedes: [],
                tags: [],
                operational_metadata: {},
              },
            ],
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(apiClient.getScenario("cs_01")).rejects.toMatchObject({
      kind: "validation",
    });
  });
});
