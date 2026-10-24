import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  categoryHealth,
  deriveCategories,
  healthOf,
  useRegressionTests,
  useRuns,
  useSamples,
} from "@/lib/api";
import type { RegressionTest } from "@/lib/types";
import { createWrapper } from "@/test/query";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SHA = "abcdef0123456789abcdef0123456789abcdef01";

function liveRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 10,
    status: "pass",
    platform: "linux",
    test_type: "commit",
    repository: "CCExtractor/ccextractor",
    branch: "master",
    commit_sha: SHA,
    pr_number: null,
    created_at: "2026-10-01T00:00:00Z",
    queued_at: null,
    started_at: null,
    completed_at: null,
    github_link: "https://github.com/CCExtractor/ccextractor/commit/" + SHA,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRuns grouping", () => {
  it("folds linux and windows for the same commit into one logical run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/runs?")) {
          return jsonResponse(200, {
            data: [
              liveRun({ run_id: 21, platform: "windows", status: "fail" }),
              liveRun({ run_id: 20, platform: "linux", status: "pass" }),
            ],
          });
        }
        return jsonResponse(404, {});
      }),
    );

    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useRuns(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));

    const run = result.current.data![0];
    expect(run.id).toBe("21");
    expect(run.commit).toBe(SHA.slice(0, 9));
    expect(run.fork).toBe("CCExtractor/ccextractor");
    expect(run.platforms.map((p) => p.platform)).toEqual(["linux", "windows"]);
    expect(run.platforms.find((p) => p.platform === "windows")?.status).toBe("fail");
    unmount();
  });

  it("keeps a PR run distinct from a commit run on the same SHA", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/runs?")) {
          return jsonResponse(200, {
            data: [
              liveRun({ run_id: 5, test_type: "pr", pr_number: 2406 }),
              liveRun({ run_id: 4, test_type: "commit", pr_number: null }),
            ],
          });
        }
        return jsonResponse(404, {});
      }),
    );

    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useRuns(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(2));
    expect(result.current.data!.map((r) => r.pr_nr).sort()).toEqual([2406, null].sort());
    unmount();
  });
});

describe("useSamples mapping", () => {
  it("normalizes extensions and keeps sample ids/shas from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/samples?")) {
          return jsonResponse(200, {
            data: [
              {
                sample_id: 14,
                sha: "abc",
                extension: "ts",
                original_name: "pal.ts",
                tags: ["pal"],
                regression_test_count: 3,
              },
              {
                sample_id: 121,
                sha: "def",
                extension: ".mkv",
                original_name: "film.mkv",
                tags: [],
                regression_test_count: 1,
              },
            ],
            pagination: { total: 2, next_offset: null },
          });
        }
        return jsonResponse(404, {});
      }),
    );

    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSamples(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(2));
    expect(result.current.data).toEqual([
      {
        id: 14,
        sha: "abc",
        extension: ".ts",
        original_name: "pal.ts",
        tags: ["pal"],
        test_count: 3,
      },
      {
        id: 121,
        sha: "def",
        extension: ".mkv",
        original_name: "film.mkv",
        tags: [],
        test_count: 1,
      },
    ]);
    unmount();
  });
});

describe("useRegressionTests", () => {
  it("joins sample SHA and ignores PR runs when folding history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/regression-tests?active=true")) {
          return jsonResponse(200, {
            data: [
              {
                regression_test_id: 7,
                sample_id: 14,
                sample_name: "pal.ts",
                command: "-autoprogram",
                input_type: "ts",
                output_type: "srt",
                expected_rc: 0,
                active: true,
                description: null,
                categories: ["General"],
              },
            ],
            pagination: { total: 1, next_offset: null },
          });
        }
        if (url.includes("/regression-tests?active=false")) {
          return jsonResponse(200, {
            data: [],
            pagination: { total: 0, next_offset: null },
          });
        }
        if (url.includes("/runs/30/samples")) {
          return jsonResponse(200, {
            data: [{ regression_test_id: 7, status: "fail", runtime_ms: 100 }],
            pagination: { total: 1, next_offset: null },
          });
        }
        if (url.includes("/runs/31/samples")) {
          return jsonResponse(200, {
            data: [{ regression_test_id: 7, status: "pass", runtime_ms: 10 }],
            pagination: { total: 1, next_offset: null },
          });
        }
        if (url.includes("/api/v1/samples?")) {
          return jsonResponse(200, {
            data: [
              {
                sample_id: 14,
                sha: "deadbeef",
                extension: ".ts",
                original_name: "pal.ts",
                tags: [],
                regression_test_count: 1,
              },
            ],
            pagination: { total: 1, next_offset: null },
          });
        }
        if (url.includes("/api/v1/runs?")) {
          return jsonResponse(200, {
            data: [
              liveRun({ run_id: 30, test_type: "commit", platform: "linux" }),
              liveRun({
                run_id: 31,
                test_type: "pr",
                pr_number: 99,
                platform: "linux",
              }),
            ],
          });
        }
        return jsonResponse(404, { message: url });
      }),
    );

    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useRegressionTests(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.data[0].sample_sha).toBe("deadbeef");
    expect(result.current.data[0].id).toBe(7);
    // PR run 31 must not contribute: only the commit failure is history.
    await waitFor(() => expect(result.current.data[0].recent_results).toEqual(["fail"]));
    expect(result.current.data[0].avg_runtime_ms).toBe(100);
    unmount();
  });
});

describe("401 handling", () => {
  it("clears the session and reloads when the API says the token is dead", async () => {
    localStorage.setItem(
      "sp-session",
      JSON.stringify({
        token: "stale",
        email: "dev@example.com",
        role: "user",
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      }),
    );
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload: vi.fn() },
    });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { message: "expired" })));

    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSamples(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    await vi.waitFor(() => {
      expect(window.location.reload).toHaveBeenCalled();
    });
    expect(localStorage.getItem("sp-session")).toBeNull();
    unmount();
  });
});

describe("healthOf / deriveCategories", () => {
  const testRow = (overrides: Partial<RegressionTest> = {}): RegressionTest => ({
    id: 1,
    sample_id: 1,
    sample_name: "a.ts",
    sample_sha: "x",
    command: "-autoprogram",
    input_type: "ts",
    output_type: "srt",
    expected_rc: 0,
    active: true,
    description: "",
    categories: ["General"],
    avg_runtime_ms: null,
    recent_results: [],
    ...overrides,
  });

  it("uses the latest non-skip result so a customized-run gap is not a failure", () => {
    expect(healthOf(testRow({ recent_results: ["fail", "skip"] }))).toBe("fail");
    expect(healthOf(testRow({ recent_results: ["fail", "pass"] }))).toBe("pass");
    expect(healthOf(testRow({ recent_results: ["skip"] }))).toBe("skip");
  });

  it("counts failing tests per category", () => {
    const tests = [
      testRow({ id: 1, categories: ["General"], recent_results: ["fail"] }),
      testRow({ id: 2, categories: ["General", "Options"], recent_results: ["pass"] }),
    ];
    expect(categoryHealth("General", tests)).toEqual({ total: 2, failing: 1 });
    expect(deriveCategories(tests).map((c) => c.name)).toEqual(["General", "Options"]);
  });
});
