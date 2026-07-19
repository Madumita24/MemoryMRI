import { render, screen } from "@testing-library/react";

import { StatusBadge } from "@/components/status-badge";

describe("StatusBadge", () => {
  it("renders the provided label", () => {
    render(<StatusBadge label="connected" tone="success" />);

    expect(screen.getByText("connected")).toBeInTheDocument();
  });
});
