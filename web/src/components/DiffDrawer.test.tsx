import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  localStorage.clear();
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
    // The pair sits one above the other with only the changed word marked.
    const removed = await screen.findByText("old");
    expect(removed.tagName).toBe("MARK");
    expect(removed.closest("div")?.textContent).toBe("−old caption");
    const added = screen.getByText("new");
    expect(added.tagName).toBe("MARK");
    expect(added.closest("div")?.textContent).toBe("+new caption");
  });

  it("explains when the output file is missing from storage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(404, { message: "not stored" })));

    const { wrapper } = createWrapper();
    render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });

    expect(
      await screen.findByText(/output file for this result isn't present in storage/i),
    ).toBeInTheDocument();
  });

  it("offers promotion to admins only, and confirms before posting it", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) =>
      String(input).includes("/baseline-approval")
        ? jsonResponse(200, { status: "approved" })
        : jsonResponse(200, { content: "" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { wrapper } = createWrapper();
    const view = render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });
    expect(screen.queryByText(/promote to baseline/i)).toBeNull();
    view.unmount();

    signIn("admin");
    render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /promote to baseline/i }));
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("baseline-approval"))).toBe(false);

    await user.click(await screen.findByRole("button", { name: "Replace baseline" }));
    expect(await screen.findByText("Baseline promoted.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls.find(([u]) => String(u).includes("baseline-approval"))!;
    expect(String(url)).toContain("/runs/21/samples/14/baseline-approval");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      regression_id: 7,
      output_id: 3,
    });
  });
});

function signIn(role: string) {
  localStorage.setItem(
    "sp-session",
    JSON.stringify({
      token: "t",
      email: "a@example.com",
      role,
      expires_at: new Date(Date.now() + 60_000).toISOString(),
    }),
  );
}
