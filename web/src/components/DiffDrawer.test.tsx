import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiffDrawer, type DiffTarget } from "@/components/DiffDrawer";
import { createWrapper } from "@/test/query";

const target: DiffTarget = {
  runId: 21,
  sampleId: 14,
  regressionId: 7,
  outputId: 3,
  command: "-autoprogram",
  sampleName: "pal.ts",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DiffDrawer", () => {
  it("renders a unified diff for a failing output", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/diff")) {
          return jsonResponse(200, {
            content: "--- expected\n+++ actual\n@@ -1 +1 @@\n-old caption\n+new caption\n",
          });
        }
        return jsonResponse(404, {});
      }),
    );

    const { wrapper } = createWrapper();
    render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });

    expect(screen.getByText("Test #7")).toBeInTheDocument();
    expect(screen.getByText(/pal\.ts/)).toBeInTheDocument();
    expect(await screen.findByText("-old caption")).toBeInTheDocument();
    expect(screen.getByText("+new caption")).toBeInTheDocument();
  });

  it("explains when the output file is missing from storage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(404, { message: "not stored" })));

    const { wrapper } = createWrapper();
    render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });

    expect(
      await screen.findByText(/output file for this result isn't present in storage/i),
    ).toBeInTheDocument();
  });
});
