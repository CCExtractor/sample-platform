import { Link } from "@tanstack/react-router";
import { ExternalLink, MoreHorizontal, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";

import { DiffDrawer, type DiffTarget } from "@/components/DiffDrawer";
import { Sparkline } from "@/components/Sparkline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import {
  promoteBaseline,
  useHealth,
  useQueue,
  useRegressionTests,
  useRunFailures,
  useRuns,
  useSamples,
  useTestHistory,
  type RunFailure,
} from "@/lib/api";
import { getSession } from "@/lib/auth";
import { githubUrl } from "@/lib/validate";
import type { LogicalRun } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Home: an inbox of recent runs that finished with failures. Each card pulls
 * that run's failing tests and groups them by category.
 *
 * Baseline promotion hides behind a per-row overflow menu and a warning
 * dialog. There is intentionally no bulk accept — replacing baselines should
 * take one deliberate click per test.
 */
export function Triage() {
  const { data: runs = [], isLoading } = useRuns();
  const { data: tests = [] } = useRegressionTests();
  const { data: health } = useHealth();

  // Latest platform runs that finished with failures — at most 3 cards.
  const failedRuns = useMemo(() => {
    const out: { run: LogicalRun; runId: number; platform: string }[] = [];
    for (const run of runs) {
      for (const p of run.platforms) {
        if (p.status === "fail" || p.status === "incomplete") {
          out.push({ run, runId: p.run_id, platform: p.platform });
        }
      }
      if (out.length >= 3) break;
    }
    return out.slice(0, 3);
  }, [runs]);

  const failingNow = tests.filter(
    (t) => t.active && t.recent_results.at(-1) === "fail",
  ).length;

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Home</h1>
          <span className="text-xs text-faint">
            recent runs that finished with failures
          </span>
          <span className="ml-auto flex items-center gap-3">
            {failingNow > 0 && (
              <span className="text-[11px] text-faint">
                {failingNow} tests red in recent runs
              </span>
            )}
            {health && (
              <span
                className="flex items-center gap-1.5 text-[11px] text-faint"
                title={health.dependencies.map((d) => `${d.name}: ${d.status}`).join("\n")}
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    health.status === "ok" ? "bg-success" : "bg-destructive",
                  )}
                />
                platform {health.status === "ok" ? "healthy" : "degraded"}
              </span>
            )}
          </span>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-6 py-5">
        <StatStrip failingNow={failingNow} />

        <SubHead>Needs triage</SubHead>
        {isLoading && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 2 }, (_, n) => `placeholder-${n}`).map((id) => (
              <div key={id} className="h-14 animate-pulse rounded-xl border bg-muted/50" />
            ))}
          </div>
        )}

        {!isLoading && failedRuns.length === 0 && (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-12 text-center">
            <ShieldCheck className="size-8 text-success" />
            <div className="text-[14px] font-medium">Nothing to triage</div>
            <p className="max-w-sm text-[13px] text-faint">
              No recent runs finished with failures. New ones land here automatically.
            </p>
          </div>
        )}

        {failedRuns.map((fr, idx) => (
          <FailureCard key={fr.runId} {...fr} defaultOpen={idx === 0} index={idx} />
        ))}

        <RecentRuns runs={runs} isLoading={isLoading} />
      </div>
    </div>
  );
}

function SubHead({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 mt-6 text-[11px] font-semibold uppercase tracking-wider text-faint first:mt-0">
      {children}
    </div>
  );
}

/**
 * Scale-and-pressure counters across the top. Everything here comes from
 * queries the page already needs, so the strip costs no extra requests.
 */
function StatStrip({ failingNow }: Readonly<{ failingNow: number }>) {
  const { data: tests = [] } = useRegressionTests();
  const { data: samples = [] } = useSamples();
  const { data: queue } = useQueue();

  const active = tests.filter((t) => t.active).length;

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Stat
        label="Failing"
        value={failingNow}
        tone={failingNow > 0 ? "bad" : "good"}
        to="/tests"
      />
      <Stat label="Active tests" value={active} hint={`${tests.length} total`} to="/tests" />
      <Stat label="Samples" value={samples.length} to="/samples" />
      <Stat
        label="Queue"
        value={queue?.meta.queue_depth ?? 0}
        hint={queue ? `${queue.meta.running_count} running` : undefined}
        to="/status"
      />
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
  to,
}: Readonly<{
  label: string;
  value: number;
  hint?: string;
  tone?: "good" | "bad";
  to: string;
}>) {
  return (
    <Link
      to={to}
      className="card-hover rounded-xl border bg-card px-3.5 py-2.5 shadow-card"
    >
      <div className="text-[10px] font-medium uppercase tracking-wider text-faint">
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className={cn(
            "text-[20px] font-semibold tabular-nums tracking-tight",
            tone === "bad" && "text-destructive",
            tone === "good" && "text-success",
          )}
        >
          {value}
        </span>
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </div>
    </Link>
  );
}

/** The last handful of runs regardless of outcome — the triage cards above
 * only show failures, which leaves the page blank on a healthy week. */
function RecentRuns({ runs, isLoading }: Readonly<{ runs: LogicalRun[]; isLoading: boolean }>) {
  const recent = runs.slice(0, 8);
  if (isLoading || recent.length === 0) return null;

  return (
    <>
      <SubHead>Recent runs</SubHead>
      <div className="overflow-hidden rounded-xl border bg-card shadow-card">
        {recent.map((run) => (
          <div
            key={run.id}
            className="flex items-center gap-3 border-b px-4 py-2 text-[13px] last:border-0"
          >
            <code className="w-24 shrink-0 truncate text-xs text-faint">
              {run.pr_nr ? `PR #${run.pr_nr}` : run.commit}
            </code>
            <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">
              {run.branch}
            </span>
            <span className="flex shrink-0 items-center gap-1">
              {run.platforms.map((p) => (
                <Link
                  key={p.run_id}
                  to="/runs/$runId"
                  params={{ runId: String(p.run_id) }}
                  title={`${p.platform} · ${p.status}`}
                  className={cn(
                    "rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition-colors",
                    p.status === "pass" && "border-success/30 text-success hover:bg-success/10",
                    p.status === "fail" &&
                      "border-destructive/30 text-destructive hover:bg-destructive/10",
                    p.status !== "pass" &&
                      p.status !== "fail" &&
                      "border-border text-faint hover:bg-muted",
                  )}
                >
                  {p.platform === "linux" ? "lnx" : "win"}
                </Link>
              ))}
            </span>
            <span className="w-24 shrink-0 text-right text-[11px] text-faint">
              {run.created_at && new Date(run.created_at).toLocaleDateString()}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

function FailureCard({
  run,
  runId,
  platform,
  defaultOpen,
  index,
}: Readonly<{
  run: LogicalRun;
  runId: number;
  platform: string;
  defaultOpen: boolean;
  index: number;
}>) {
  const [open, setOpen] = useState(defaultOpen);
  const { data: failures = [], isLoading } = useRunFailures(open ? runId : null);
  const gh = githubUrl(run.github_link);

  // Group by first category, biggest group first.
  const groups = useMemo(() => {
    const byCat = new Map<string, RunFailure[]>();
    for (const f of failures) {
      const cat = f.categories[0] ?? "Uncategorized";
      byCat.set(cat, [...(byCat.get(cat) ?? []), f]);
    }
    return [...byCat.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [failures]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      className="mb-3"
    >
      <div
        className={cn(
          "card-hover overflow-hidden rounded-xl border bg-card shadow-card",
          open && "border-border-strong",
        )}
      >
        <button
          className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left"
          onClick={() => setOpen(!open)}
        >
          <span
            className={cn(
              "w-9 shrink-0 rounded-md border px-1 py-0.5 text-center text-[10px] font-semibold uppercase tracking-wide",
              platform === "windows"
                ? "border-destructive/30 text-destructive"
                : "border-warning/40 text-warning",
            )}
          >
            {platform === "linux" ? "lnx" : "win"}
          </span>
          <div className="min-w-0 flex-1 text-[13px]">
            <span className="font-medium">
              {run.pr_nr ? `PR #${run.pr_nr}` : `commit ${run.commit}`}
            </span>{" "}
            <span className="text-muted-foreground">
              finished with failures on {platform}
            </span>
          </div>
          {open && !isLoading && (
            <Badge variant="destructive">{failures.length} failing</Badge>
          )}
        </button>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
              className="overflow-hidden"
            >
              <div className="border-t bg-muted/30">
                {isLoading && (
                  <div className="flex flex-col gap-1 p-3">
                    {Array.from({ length: 3 }, (_, n) => `placeholder-${n}`).map((id) => (
                      <div key={id} className="h-8 animate-pulse rounded-lg bg-muted" />
                    ))}
                  </div>
                )}
                {groups.map(([cat, items]) => (
                  <div key={cat}>
                    <div className="border-b bg-muted/50 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
                      {cat} · {items.length}
                    </div>
                    {items.slice(0, 5).map((f) => (
                      <FailureRow key={f.regression_test_id} f={f} runId={runId} />
                    ))}
                    {items.length > 5 && (
                      <div className="border-b px-4 py-1.5 text-[11px] text-faint">
                        + {items.length - 5} more in {cat}
                      </div>
                    )}
                  </div>
                ))}
                <div className="flex items-center gap-2 bg-card px-4 py-2.5">
                  {gh && (
                    <a href={gh} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="ghost">
                        <ExternalLink /> Open on GitHub
                      </Button>
                    </a>
                  )}
                  <span className="ml-auto text-[11px] text-faint">
                    run {runId}
                  </span>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function FailureRow({ f, runId }: Readonly<{ f: RunFailure; runId: number }>) {
  const admin = getSession()?.role === "admin";
  const [menu, setMenu] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [diff, setDiff] = useState<DiffTarget | null>(null);
  // Shares the query the tests list already made, so this costs no fetch.
  const { data: history } = useTestHistory();
  const past = history?.get(f.regression_test_id);
  const output = f.outputs.find((o) => o.status === "fail") ?? f.outputs[0];

  const doPromote = async () => {
    if (!output) return;
    setBusy(true);
    const res = await promoteBaseline({
      runId,
      sampleId: f.sample_id,
      regressionId: f.regression_test_id,
      outputId: output.output_id,
    });
    setBusy(false);
    setConfirming(false);
    setResult(res.ok ? "Baseline promoted." : res.message);
  };

  return (
    <div className="group relative flex items-center gap-3 border-b px-4 py-2 text-[13px] transition-colors hover:bg-card">
      <Link
        to="/tests"
        search={{ t: f.regression_test_id }}
        className="flex min-w-0 flex-1 items-center gap-3"
      >
        <code className="w-12 shrink-0 text-xs text-faint">#{f.regression_test_id}</code>
        <code className="min-w-0 flex-1 truncate text-xs text-foreground/85">{f.command}</code>
        <span className="w-32 shrink-0 truncate text-[11px] text-faint">{f.sample_name}</span>
        {past && (
          <Sparkline results={past.recent_results.filter((r) => r !== "skip").slice(-10)} />
        )}
      </Link>

      {result && <span className="shrink-0 text-[11px] text-faint">{result}</span>}

      {output && (
        <button
          className="shrink-0 cursor-pointer rounded-md border px-1.5 py-0.5 text-[11px] text-faint opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100"
          onClick={() =>
            setDiff({
              runId,
              sampleId: f.sample_id,
              regressionId: f.regression_test_id,
              outputId: output.output_id,
              command: f.command,
              sampleName: f.sample_name,
            })
          }
        >
          diff
        </button>
      )}

      {admin && output && !result && (
        <div className="relative shrink-0">
          <button
            className="cursor-pointer rounded-md p-1 text-faint opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover:opacity-100"
            onClick={() => setMenu(!menu)}
          >
            <MoreHorizontal className="size-4" />
          </button>
          {menu && (
            <div className="absolute right-0 top-7 z-20 w-56 rounded-lg border bg-card p-1 shadow-pop">
              <button
                className="w-full cursor-pointer rounded-md px-2.5 py-1.5 text-left text-xs text-destructive transition-colors hover:bg-destructive/10"
                onClick={() => {
                  setMenu(false);
                  setConfirming(true);
                }}
              >
                Promote this output to baseline…
              </button>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Replace baseline of test #${f.regression_test_id}?`}
        body={
          <>
            The output this run produced becomes the expected baseline{" "}
            <b>for every future run, on all platforms</b>. The current baseline hash
            is discarded, and the only way back is promoting another output.
          </>
        }
        confirmLabel={busy ? "Promoting…" : "Replace baseline"}
        busy={busy}
        onConfirm={doPromote}
      />

      <DiffDrawer target={diff} onClose={() => setDiff(null)} />
    </div>
  );
}
