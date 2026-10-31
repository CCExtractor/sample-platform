import { ChevronDown, ExternalLink, GitCommitHorizontal, GitPullRequest, Timer } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { Link } from "@tanstack/react-router";

import { RunStatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRunFailures, useRuns, useRunSummary } from "@/lib/api";
import { githubUrl } from "@/lib/validate";
import type { LogicalPlatformRun, LogicalRun } from "@/lib/types";
import { cn } from "@/lib/utils";

/** CI runs, newest first, with Linux and Windows grouped per commit. */
/**
 * Timeline dot for a commit: red if either platform broke, green only when
 * both passed, grey while anything is still unresolved.
 */
function dotColour(run: LogicalRun): string {
  if (run.platforms.some((p) => p.status === "fail" || p.status === "error")) {
    return "bg-destructive";
  }
  return run.platforms.every((p) => p.status === "pass") ? "bg-success" : "bg-faint";
}

export function Runs() {
  const { data: runs = [], isLoading } = useRuns();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Test results</h1>
          <span className="text-xs text-faint">
            Linux and Windows grouped per commit · refreshes every 30s
          </span>
          <Link to="/runs/new" className="ml-auto">
            <Button size="sm" variant="secondary">New run</Button>
          </Link>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-6 py-4">
        {isLoading && <ListSkeleton />}
        {runs.map((run, i) => (
          <motion.div
            key={run.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.22 }}
            className="group relative pb-3 pl-6"
          >
            <span className="absolute left-[7px] top-6 h-full w-px bg-border group-last:hidden" />
            <span
              className={cn(
                "absolute left-0 top-4 size-[15px] rounded-full border-2 border-card",
                dotColour(run),
              )}
            />

            <div
              className={cn(
                "card-hover overflow-hidden rounded-xl border bg-card shadow-card",
                open === run.id && "border-border-strong",
              )}
            >
              <button
                className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-3 text-left"
                onClick={() => setOpen(open === run.id ? null : run.id)}
              >
                {run.pr_nr ? (
                  <Badge variant="accent">
                    <GitPullRequest className="size-3" /> #{run.pr_nr}
                  </Badge>
                ) : (
                  <Badge variant="secondary">
                    <GitCommitHorizontal className="size-3" /> {run.branch}
                  </Badge>
                )}
                <code className="text-xs text-faint">{run.commit}</code>
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {run.fork}
                </span>
                {run.created_at && (
                  <span className="shrink-0 text-[11px] text-faint">
                    {new Date(run.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}
                  </span>
                )}
                <div className="flex shrink-0 items-center gap-4">
                  {run.platforms.map((p) => (
                    <span key={p.platform} className="flex items-center gap-1.5">
                      <span className="w-7 text-[10px] font-semibold uppercase tracking-wider text-faint">
                        {p.platform === "linux" ? "lnx" : "win"}
                      </span>
                      <RunStatusBadge status={p.status} />
                    </span>
                  ))}
                </div>
                <ChevronDown
                  className={cn(
                    "size-4 shrink-0 text-faint transition-transform duration-200",
                    open === run.id && "rotate-180",
                  )}
                />
              </button>

              <AnimatePresence initial={false}>
                {open === run.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
                    className="overflow-hidden"
                  >
                    <RunDetail run={run} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function RunDetail({ run }: Readonly<{ run: LogicalRun }>) {
  const gh = githubUrl(run.github_link);
  return (
    <div className="border-t">
      <div className="grid grid-cols-2 gap-px bg-border">
        {run.platforms.map((p) => (
          <PlatformDetail key={p.platform} p={p} />
        ))}
      </div>
      {gh && (
        <div className="border-t bg-muted/30 px-4 py-2">
          <a
            href={gh}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
          >
            <ExternalLink className="size-3" /> View on GitHub
          </a>
        </div>
      )}
    </div>
  );
}

/** Counts arrive lazily from GET /runs/<id>/summary when the row expands. */
function PlatformDetail({ p }: Readonly<{ p: LogicalPlatformRun }>) {
  const { data: s, isLoading } = useRunSummary(p.run_id);
  const hasFailures = (s?.fail_count ?? 0) + (s?.error_count ?? 0) > 0;
  const { data: failures = [] } = useRunFailures(hasFailures ? p.run_id : null);
  const dur = s?.duration_ms != null ? Math.round(s.duration_ms / 60000) : null;

  return (
    <div className="bg-card p-4">
      <div className="mb-2.5 flex items-center justify-between">
        <Link
          to="/runs/$runId"
          params={{ runId: String(p.run_id) }}
          className="group text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {p.platform}{" "}
          <span className="ml-1 font-normal normal-case text-faint group-hover:text-primary group-hover:underline">
            run {p.run_id} →
          </span>
        </Link>
        <span className="flex items-center gap-2 text-[11px] text-faint">
          {dur != null && (
            <>
              <Timer className="size-3" /> {dur}m
            </>
          )}
          <RunStatusBadge status={p.status} />
        </span>
      </div>

      {isLoading && <div className="h-10 animate-pulse rounded-lg bg-muted" />}

      {s && (
        <>
          <div className="mb-2 flex h-1.5 overflow-hidden rounded-full bg-muted">
            {s.total_samples > 0 && (
              <>
                <motion.span
                  className="bg-success"
                  initial={{ width: 0 }}
                  animate={{ width: `${(s.pass_count / s.total_samples) * 100}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
                <motion.span
                  className="bg-destructive"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${((s.fail_count + s.error_count) / s.total_samples) * 100}%`,
                  }}
                  transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
                />
                <motion.span
                  className="bg-warning"
                  initial={{ width: 0 }}
                  animate={{ width: `${(s.missing_output_count / s.total_samples) * 100}%` }}
                  transition={{ duration: 0.5, ease: "easeOut", delay: 0.2 }}
                />
              </>
            )}
          </div>
          <div className="text-[11px] tabular-nums text-faint">
            <span className="text-success">{s.pass_count} passed</span>
            {" · "}
            <span className={s.fail_count + s.error_count > 0 ? "text-destructive" : ""}>
              {s.fail_count + s.error_count} failed
            </span>
            {" · "}
            {s.missing_output_count} missing output · {s.skipped_count} skipped ·{" "}
            {s.total_samples} total
          </div>
          {failures.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {failures.slice(0, 14).map((f) => (
                <Link
                  key={f.regression_test_id}
                  to="/tests"
                  search={{ t: f.regression_test_id }}
                  title={`${f.command} — ${f.sample_name}`}
                  className="rounded-md border bg-destructive/5 px-1.5 py-0.5 font-mono text-[11px] text-destructive transition-colors hover:bg-destructive/15"
                >
                  #{f.regression_test_id}
                </Link>
              ))}
              {failures.length > 14 && (
                <span className="px-1 text-[11px] text-faint">+{failures.length - 14}</span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: 4 }, (_, n) => `placeholder-${n}`).map((id) => (
        <div key={id} className="h-12 animate-pulse rounded-xl border bg-muted/50" />
      ))}
    </div>
  );
}
