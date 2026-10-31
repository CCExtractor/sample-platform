import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ChevronLeft, GitBranch, Loader2, Play, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createRun, deriveCategories, useRegressionTests } from "@/lib/api";
import { isBranchName, isCommitSha, isRepoSlug } from "@/lib/validate";
import type { Platform } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Start a run against any fork/commit — replaces the old "Customized tests"
 * page. POSTs one run per selected platform via POST /api/v1/runs.
 */
export function RunNew() {
  const { data: tests = [] } = useRegressionTests();
  const navigate = useNavigate();
  const search = useSearch({ from: "/runs/new" });

  // Set when arriving from the test builder: run just this one test.
  const [onlyTest, setOnlyTest] = useState<number | undefined>(search.test);

  const [repository, setRepository] = useState("CCExtractor/ccextractor");
  const [branch, setBranch] = useState("master");
  const [commit, setCommit] = useState("");
  const [platforms, setPlatforms] = useState<Platform[]>(["linux", "windows"]);
  const [cats, setCats] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const categories = deriveCategories(tests);
  const commitOk = isCommitSha(commit);
  const repoOk = isRepoSlug(repository);
  const branchOk = isBranchName(branch);

  const selectedIds = useMemo(() => {
    if (onlyTest !== undefined) return [onlyTest];
    if (cats.length === 0) return undefined; // full suite
    return tests
      .filter((t) => t.active && t.categories.some((c) => cats.includes(c)))
      .map((t) => t.id);
  }, [onlyTest, cats, tests]);

  const estimate = useMemo(() => {
    if (onlyTest !== undefined) return { count: 1, minutes: 1 };
    const pool =
      selectedIds === undefined
        ? tests.filter((t) => t.active)
        : tests.filter((t) => selectedIds.includes(t.id));
    const ms = pool.reduce((acc, t) => acc + (t.avg_runtime_ms ?? 15_000), 0);
    return { count: pool.length, minutes: Math.max(1, Math.round(ms / 60_000)) };
  }, [onlyTest, selectedIds, tests]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await Promise.all(
        platforms.map((platform) =>
          createRun({
            commit_sha: commit,
            platform,
            branch,
            repository,
            ...(selectedIds ? { regression_test_ids: selectedIds } : {}),
          }),
        ),
      );
      navigate({ to: "/runs" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to queue run");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="mb-7 flex items-center gap-3">
        <Link to="/runs">
          <Button variant="ghost" size="icon"><ChevronLeft /></Button>
        </Link>
        <div>
          <h1 className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
            <GitBranch className="size-4 text-primary" /> New run
          </h1>
          <p className="text-[13px] text-faint">
            Run the regression suite against any fork or commit.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Repository</Label>
            <Input
              value={repository}
              onChange={(e) => setRepository(e.target.value)}
              placeholder="owner/repo"
              className={cn(!repoOk && repository && "border-destructive/50")}
            />
          </div>
          <div>
            <Label>Branch</Label>
            <Input
              value={branch}
              onChange={(e) => setBranch(e.target.value.trim())}
              className={cn(!branchOk && branch && "border-destructive/50")}
            />
          </div>
        </div>

        <div>
          <Label>Commit SHA (full 40 characters)</Label>
          <Input
            value={commit}
            onChange={(e) => setCommit(e.target.value.trim())}
            placeholder="e.g. cf7c396176271462b9a29c62a1c3c6d8b723bd2b"
            className={cn("font-mono text-xs", !commitOk && commit && "border-destructive/50")}
          />
        </div>

        <div>
          <Label>Platforms</Label>
          <div className="flex gap-2">
            {(["linux", "windows"] as Platform[]).map((p) => {
              const on = platforms.includes(p);
              return (
                <button
                  key={p}
                  onClick={() =>
                    setPlatforms(on ? platforms.filter((x) => x !== p) : [...platforms, p])
                  }
                  className={cn(
                    "cursor-pointer rounded-lg border px-4 py-2 text-[13px] font-medium capitalize transition-all duration-150",
                    on
                      ? "border-primary/50 bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {p}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <Label>
            Scope <span className="font-normal normal-case">— empty = full suite</span>
          </Label>
          {onlyTest !== undefined && (
            <div className="mb-2 flex items-center gap-2 rounded-lg border border-primary/40 bg-accent/40 px-3 py-2 text-[12px]">
              <span>
                Verification run for test <b>#{onlyTest}</b> only
              </span>
              <button
                onClick={() => setOnlyTest(undefined)}
                title="Run the full suite instead"
                className="ml-auto cursor-pointer rounded p-0.5 text-faint hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}
          <div className={cn("flex flex-wrap gap-1.5", onlyTest !== undefined && "hidden")}>
            {categories.map((c) => {
              const on = cats.includes(c.name);
              return (
                <button
                  key={c.name}
                  onClick={() =>
                    setCats(on ? cats.filter((x) => x !== c.name) : [...cats, c.name])
                  }
                  className={cn(
                    "cursor-pointer rounded-full border px-3 py-1 text-xs transition-all duration-150",
                    on
                      ? "border-primary bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {c.name} <span className="opacity-60">{c.test_count}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between rounded-xl border bg-muted/30 p-4">
          <span className="text-[12px] text-faint">
            ~{estimate.count} tests · est. {estimate.minutes} min per platform ×{" "}
            {platforms.length} platform{platforms.length === 1 ? "" : "s"}
          </span>
          <div className="flex items-center gap-2">
            {error && <span className="text-[11px] text-destructive">{error}</span>}
            <Button
              disabled={!commitOk || !repoOk || !branchOk || platforms.length === 0 || busy}
              onClick={submit}
            >
              {busy ? <Loader2 className="animate-spin" /> : <Play />} Queue run
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Label({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}
