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

  describe("Smart view", () => {
    /** Serve one smart-diff body and record which URLs were asked for. */
    function serveSmart(status: number, body: unknown) {
      const calls: string[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input);
          calls.push(url);
          if (url.includes("format=smart")) return jsonResponse(status, body);
          return jsonResponse(200, { content: "" });
        }),
      );
      return calls;
    }

    async function openSmart() {
      const user = userEvent.setup();
      const { wrapper } = createWrapper();
      render(<DiffDrawer target={target} onClose={vi.fn()} />, { wrapper });
      await user.click(screen.getByRole("button", { name: /smart/i }));
    }

    it("asks the diff endpoint for the smart format", async () => {
      const calls = serveSmart(200, {
        kind: "identical",
        summary: "Outputs are identical.",
        expected_cues: 3,
        actual_cues: 3,
      });

      await openSmart();

      expect(await screen.findByText("Identical")).toBeInTheDocument();
      expect(calls.some((u) => u.endsWith("/regression-tests/7/outputs/3/diff?format=smart"))).toBe(
        true,
      );
    });

    it("names a timing shift and its offset", async () => {
      serveSmart(200, {
        kind: "timing_shift",
        summary: "All 2 cues match but are 500 ms late.",
        expected_cues: 2,
        actual_cues: 2,
        offset_ms: 500,
        changes: [
          { cue: 1, kind: "timing", offset_ms: 500 },
          { cue: 2, kind: "timing", offset_ms: 500 },
        ],
      });

      await openSmart();

      expect(await screen.findByText("Timing shift")).toBeInTheDocument();
      expect(screen.getByText("All 2 cues match but are 500 ms late.")).toBeInTheDocument();
      expect(screen.getByText("2 expected · 2 actual cues")).toBeInTheDocument();
      expect(screen.getByText("Cue 1")).toBeInTheDocument();
      expect(screen.getAllByText("+500 ms")).toHaveLength(3);
    });

    it("shows expected and actual text for a changed cue", async () => {
      serveSmart(200, {
        kind: "text_change",
        summary: "1 of 1 cues differ in text.",
        expected_cues: 1,
        actual_cues: 1,
        changes: [{ cue: 1, kind: "text", expected: "Hello there", actual: "Goodbye" }],
      });

      await openSmart();

      expect(await screen.findByText("Text changed")).toBeInTheDocument();
      expect(screen.getByText("- Hello there")).toBeInTheDocument();
      expect(screen.getByText("+ Goodbye")).toBeInTheDocument();
    });

    it("renders caption text as text, never as markup", async () => {
      serveSmart(200, {
        kind: "text_change",
        summary: "<b>bold</b> summary",
        expected_cues: 1,
        actual_cues: 1,
        changes: [{ cue: 1, kind: "text", expected: "<i>a</i>", actual: "<script>x</script>" }],
      });

      await openSmart();

      expect(await screen.findByText("<b>bold</b> summary")).toBeInTheDocument();
      expect(screen.getByText("+ <script>x</script>")).toBeInTheDocument();
      expect(document.querySelector("script")).toBeNull();
    });

    it("says when only some changed cues are listed", async () => {
      serveSmart(200, {
        kind: "mixed",
        summary: "Mixed differences across 30 compared cues; expected 30, got 30.",
        expected_cues: 30,
        actual_cues: 30,
        changes: Array.from({ length: 25 }, (_, n) => ({ cue: n + 1, kind: "whitespace" })),
        changes_truncated: true,
      });

      await openSmart();

      expect(await screen.findByText("Mixed changes")).toBeInTheDocument();
      expect(screen.getByText("Only the first 25 changed cues are listed.")).toBeInTheDocument();
    });

    it("points to the Diff tab for outputs without captions", async () => {
      serveSmart(200, {
        kind: "unsupported",
        summary: "No subtitle cues to compare (unsupported format); see the raw diff.",
        expected_cues: 0,
        actual_cues: 0,
      });

      await openSmart();

      expect(await screen.findByText("Not a caption file")).toBeInTheDocument();
      expect(screen.getByText(/diff tab shows this output line by line/i)).toBeInTheDocument();
    });

    it("explains when the output file is missing from storage", async () => {
      serveSmart(404, { message: "not stored" });

      await openSmart();

      expect(
        await screen.findByText(/output file for this result isn't present in storage/i),
      ).toBeInTheDocument();
    });

    it("is not offered for the combined-stdout diff", () => {
      serveSmart(200, {});
      const { wrapper } = createWrapper();
      render(<DiffDrawer target={{ kind: "console", runId: 21 }} onClose={vi.fn()} />, { wrapper });

      expect(screen.queryByRole("button", { name: /smart/i })).toBeNull();
    });
  });
});
