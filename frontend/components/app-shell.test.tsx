import { render, screen } from "@testing-library/react";

import { AppShell } from "@/components/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/investigations",
}));

vi.mock("@/components/api-connection-badge", () => ({
  ApiConnectionBadge: () => <span>connected</span>,
}));

describe("AppShell", () => {
  const originalEnv = process.env;

  beforeAll(() => {
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "true",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "false",
    };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("renders the stable navigation routes", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /benchmarks/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /investigations/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verification/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /artifacts/i })).toBeInTheDocument();
    expect(screen.getByText(/demo mode/i)).toBeInTheDocument();
  });
});
