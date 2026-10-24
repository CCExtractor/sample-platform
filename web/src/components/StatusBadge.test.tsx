import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatusBadge } from "@/components/StatusBadge";

describe("RunStatusBadge", () => {
  it("labels failed and passed runs", () => {
    const { rerender } = render(<RunStatusBadge status="fail" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
    rerender(<RunStatusBadge status="pass" />);
    expect(screen.getByText("Passed")).toBeInTheDocument();
  });

  it("treats completed as a finished success, not still-running", () => {
    render(<RunStatusBadge status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });
});
