import { render, screen } from "@testing-library/react";

import OverviewPage from "@/app/page";
import { ApiClientError } from "@/lib/api/client";

const hooksMock = vi.hoisted(() => ({
  useHealthQuery: vi.fn(),
  useDomainsQuery: vi.fn(),
  useScenariosQuery: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => hooksMock);

describe("OverviewPage", () => {
  const originalEnv = process.env;

  beforeAll(() => {
    process.env = {
      ...originalEnv,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ENABLE_LIVE_RUNS: "false",
    };
  });

  beforeEach(() => {
    hooksMock.useHealthQuery.mockReset();
    hooksMock.useDomainsQuery.mockReset();
    hooksMock.useScenariosQuery.mockReset();
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("shows loading state while queries are pending", () => {
    hooksMock.useHealthQuery.mockReturnValue({
      isError: false,
      isLoading: true,
      dataUpdatedAt: 0,
    });
    hooksMock.useDomainsQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      dataUpdatedAt: 0,
    });
    hooksMock.useScenariosQuery.mockReturnValue({
      isLoading: true,
      isError: false,
      dataUpdatedAt: 0,
    });

    render(<OverviewPage />);

    expect(screen.getAllByTestId("loading-skeleton").length).toBeGreaterThan(0);
  });

  it("shows backend unavailable state when health fails", () => {
    hooksMock.useHealthQuery.mockReturnValue({
      isError: true,
      error: new ApiClientError("Backend down", { kind: "network" }),
      refetch: vi.fn(),
    });
    hooksMock.useDomainsQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      dataUpdatedAt: 0,
    });
    hooksMock.useScenariosQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      dataUpdatedAt: 0,
    });

    render(<OverviewPage />);

    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
