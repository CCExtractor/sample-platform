import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import {
  AlertTriangle,
  Ban,
  Binary,
  Bug,
  Check,
  ChevronDown,
  ChevronLeft,
  Download,
  ExternalLink,
  FileText,
  GitCommitHorizontal,
  GitPullRequest,
  Loader2,
  RotateCcw,
  Terminal,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";

import { DiffDrawer, type DiffTarget } from "@/components/DiffDrawer";
import { RunStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import {
  cancelRun,
  restartRun,
  fetchRunLog,
  useInfraErrors,
  useRun,
  useRunArtifacts,
  useRunProgress,
  useRunSamples,
  type RunArtifact,
  type RunFailure,
} from "@/lib/api";
import { canOperateCi, getSession } from "@/lib/auth";
import { githubUrl, httpsUrl } from "@/lib/validate";
import { cn } from "@/lib/utils";

const STAGES = ["preparation", "testing", "completed"] as const;
const STAGE_LABEL: Record<string, string> = {
  preparation: "Preparation",
  testing: "Testing",
  completed: "Completed",
  canceled: "Canceled",
};

/**
 * One platform run: metadata, progress stepper, and results grouped by
 * category. Failing tests open their diff in a drawer.
 */
export function RunDetail() {
  const { runId } = useParams({ from: "/runs/$runId" });
  const id = Number(runId);
  const { data: run } = useRun(id);
  const { data: progress = [] } = useRunProgress(id);
  const { data: samples = [], isLoading } = useRunSamples(id);
  const { data: infraErrors = [] } = useInfraErrors(id);
  const gh = githubUrl(run?.github_link);
  const qc = useQueryClient();

  // Reached-stage set for the stepper.
  const reached = new Set(progress.map((p) => p.status));
  const canceled = reached.has("canceled");

  const finished =
    !run || ["pass", "fail", "canceled", "error"].includes(run.status);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const doRestart = async () => {
    setRestarting(true);
    try {
      await restartRun(id);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["run", id] }),
        qc.invalidateQueries({ queryKey: ["run-progress", id] }),
        qc.invalidateQueries({ queryKey: ["runs"] }),
      ]);
    } finally {
      setRestarting(false);
      setConfirmRestart(false);
    }
  };

  const doCancel = async () => {
    setCanceling(true);
    try {
      await cancelRun(id);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["run", id] }),
        qc.invalidateQueries({ queryKey: ["run-progress", id] }),
        qc.invalidateQueries({ queryKey: ["runs"] }),
      ]);
    } finally {
      setCanceling(false);
      setConfirmCancel(false);
    }
  };

  // Group results by category; a category "fails" if any test in it fails.
  const categories = useMemo(() => {
    const byCat = new Map<string, RunFailure[]>();
    for (const s of samples) {
      const cat = s.categories[0] ?? "Uncategorized";
      byCat.set(cat, [...(byCat.get(cat) ?? []), s]);
    }
    return [...byCat.entries()]
      .map(([name, rows]) => ({
        name,
        rows,
        failed: rows.filter((r) => r.status !== "pass").length,
      }))
      .sort((a, b) => b.failed - a.failed || a.name.localeCompare(b.name));
  }, [samples]);

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <Link to="/runs">
            <Button variant="ghost" size="icon"><ChevronLeft /></Button>
          </Link>
          <h1 className="text-[15px] font-semibold tracking-tight">Run {id}</h1>
          {run && <RunStatusBadge status={run.status} />}
          <div className="ml-auto flex items-center gap-2">
            {!finished && canOperateCi(getSession()) && (
              <Button size="sm" variant="outline" onClick={() => setConfirmCancel(true)}>
                <Ban /> Cancel run
              </Button>
            )}
            {finished && canOperateCi(getSession()) && (
              <Button size="sm" variant="outline" onClick={() => setConfirmRestart(true)}>
                <RotateCcw /> Run again
              </Button>
            )}
            {gh && (
              <a href={gh} target="_blank" rel="noreferrer">
                <Button size="sm" variant="secondary">
                  <ExternalLink /> View on GitHub
                </Button>
              </a>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmRestart}
        onOpenChange={setConfirmRestart}
        title={`Run ${id} again?`}
        body={
          <>
            The results and the progress trail for this run are cleared so CI
            picks it up again. The run keeps its id, and{" "}
            <b>the existing results are replaced, not kept alongside</b>.
          </>
        }
        confirmLabel={restarting ? "Queueing…" : "Run again"}
        busy={restarting}
        onConfirm={doRestart}
      />

      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title={`Cancel run ${id}?`}
        body="The VM stops as soon as it notices, and results collected so far are kept. This can't be resumed — a new run has to be queued."
        confirmLabel={canceling ? "Canceling…" : "Cancel run"}
        busy={canceling}
        onConfirm={doCancel}
      />

      <div className="mx-auto max-w-4xl px-6 py-5">
        {infraErrors.length > 0 && (
          <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-warning/40 bg-warning/8 p-3.5">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <div className="text-[13px]">
              <div className="font-medium text-warning">
                Infrastructure problem — failures here may not be caused by the code
              </div>
              <ul className="mt-1 text-[12px] text-muted-foreground">
                {infraErrors.slice(0, 3).map((e) => (
                  <li key={`${e.type}-${e.message}`}>
                    <span className="uppercase text-[10px] tracking-wider text-faint">{e.type}</span>{" "}
                    {e.message}
                  </li>
                ))}
                {infraErrors.length > 3 && (
                  <li className="text-faint">+ {infraErrors.length - 3} more</li>
                )}
              </ul>
            </div>
          </div>
        )}

        {/* Metadata */}
        {run && (
          <div className="mb-6 overflow-hidden rounded-xl border shadow-card">
            <MetaRow label={run.pr_number ? "Pull request" : "Commit"}>
              {run.pr_number ? (
                <span className="inline-flex items-center gap-1.5">
                  <GitPullRequest className="size-3.5 text-primary" />
                  {gh ? (
                    <a href={gh} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                      #{run.pr_number}
                    </a>
                  ) : (
                    <span className="text-primary">#{run.pr_number}</span>
                  )}
                  <span className="text-faint">(commit {run.commit_sha.slice(0, 7)})</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <GitCommitHorizontal className="size-3.5" /> {run.commit_sha.slice(0, 9)}
                </span>
              )}
            </MetaRow>
            <MetaRow label="Platform"><span className="capitalize">{run.platform}</span></MetaRow>
            <MetaRow label="Repository">{run.repository}</MetaRow>
            <MetaRow label="Branch">{run.branch}</MetaRow>
            <MetaRow label="Start time">{fmt(run.started_at ?? run.created_at)}</MetaRow>
            <MetaRow label="End time" last>{fmt(run.completed_at)}</MetaRow>
          </div>
        )}

        {/* Progress stepper */}
        <div className="mb-8 px-4">
          <div className="flex items-center">
            {STAGES.map((stage, i) => {
              const done = reached.has(stage) || (stage === "completed" && reached.has("completed"));
              const isCanceledEnd = canceled && stage === "completed";
              return (
                <div key={stage} className="flex flex-1 items-center last:flex-none">
                  <div className="flex flex-col items-center gap-1.5">
                    <div className="text-[11px] font-medium text-muted-foreground">
                      {isCanceledEnd ? "Canceled" : STAGE_LABEL[stage]}
                    </div>
                    <div
                      className={cn(
                        "flex size-6 items-center justify-center rounded-full border-2 transition-colors",
                        done && !isCanceledEnd && "border-success bg-success text-white",
                        isCanceledEnd && "border-faint bg-faint text-white",
                        !done && !isCanceledEnd && "border-border bg-card text-faint",
                      )}
                    >
                      {done && <Check className="size-3.5" />}
                    </div>
                  </div>
                  {i < STAGES.length - 1 && (
                    <div
                      className={cn(
                        "mx-1 mt-5 h-0.5 flex-1 rounded",
                        reached.has(STAGES[i + 1]) ? "bg-success" : "bg-border",
                      )}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {finished && <ArtifactsSection runId={id} samples={samples} />}

        {/* Results by category */}
        <h2 className="mb-1 text-[15px] font-semibold tracking-tight">Test results</h2>
        <p className="mb-3 text-[13px] text-faint">
          Click a category to expand; click a failing test to see its diff.
        </p>
        {isLoading && (
          <div className="flex flex-col gap-1.5">
            {Array.from({ length: 6 }, (_, n) => `placeholder-${n}`).map((id) => (
              <div key={id} className="h-9 animate-pulse rounded-lg bg-muted/60" />
            ))}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          {categories.map((c) => (
            <CategoryBlock key={c.name} {...c} runId={id} />
          ))}
        </div>
      </div>
    </div>
  );
}

function CategoryBlock({
  name, rows, failed, runId,
}: Readonly<{
  name: string;
  rows: RunFailure[];
  failed: number;
  runId: number;
}>) {
  const [open, setOpen] = useState(failed > 0);
  const [diff, setDiff] = useState<DiffTarget | null>(null);

  return (
    <div className="overflow-hidden rounded-lg border">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center gap-2 bg-card px-3 py-2 text-left transition-colors hover:bg-muted/50"
      >
        <ChevronDown className={cn("size-4 text-faint transition-transform", open && "rotate-180")} />
        <span className={cn("text-[13px] font-medium", failed > 0 ? "text-destructive" : "text-success")}>
          {name} — {failed > 0 ? `${failed} failed` : "Pass"}
        </span>
        <span className="ml-auto text-[11px] text-faint">{rows.length} tests</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t bg-muted/20">
              {rows.map((r) => {
                const failing = r.status !== "pass";
                const output = r.outputs.find((o) => o.status === "fail") ?? r.outputs[0];
                return (
                  <div
                    key={r.regression_test_id}
                    className="flex items-center gap-2.5 border-b px-3 py-1.5 text-[12px] last:border-0"
                  >
                    <span
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        r.status === "pass" && "bg-success",
                        failing && "bg-destructive",
                      )}
                    />
                    <Link
                      to="/tests"
                      search={{ t: r.regression_test_id }}
                      className="flex min-w-0 flex-1 items-center gap-2 hover:underline"
                    >
                      <code className="text-faint">#{r.regression_test_id}</code>
                      <code className="min-w-0 flex-1 truncate">{r.command}</code>
                    </Link>
                    {failing && output ? (
                      <button
                        className="shrink-0 cursor-pointer font-medium text-destructive hover:underline"
                        onClick={() =>
                          setDiff({
                            runId,
                            sampleId: r.sample_id,
                            regressionId: r.regression_test_id,
                            outputId: output.output_id,
                            command: r.command,
                            sampleName: r.sample_name,
                          })
                        }
                      >
                        Fail
                      </button>
                    ) : (
                      <span
                        className={cn(
                          "shrink-0 text-[11px]",
                          r.status === "pass" ? "text-success" : "text-warning",
                        )}
                      >
                        {r.status === "pass" ? "Pass" : r.status}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <DiffDrawer target={diff} onClose={() => setDiff(null)} />
    </div>
  );
}

/** One expected-vs-actual output, paired from the run's artifacts. A single
 * regression-test output can carry several accepted expected variants. */
interface OutputComparison {
  key: string;
  rtId: number;
  outputId: number;
  ext: string;
  expected: RunArtifact[];
  actual: RunArtifact | null;
}

/** Run-level (non per-output) artifacts, in display order. */
const RUN_FILE_TYPES = ["build_log", "binary", "coredump", "combined_stdout"] as const;
const RUN_FILE_LABEL: Record<string, string> = {
  build_log: "Build log",
  binary: "Binary",
  coredump: "Core dump",
  combined_stdout: "Combined stdout",
};
const RUN_FILE_ICON: Record<string, typeof FileText> = {
  build_log: FileText,
  binary: Binary,
  coredump: Bug,
  combined_stdout: Terminal,
};

/** Recover the (regression-test, output) a per-output artifact belongs to from
 * its id — the backend encodes it as `expected|actual_{run}_{rt}_{output}`. */
function parseOutputKey(id: string): { rtId: number; outputId: number } | null {
  const m = /^(?:expected|actual)_\d+_(\d+)_(\d+)$/.exec(id);
  return m ? { rtId: Number(m[1]), outputId: Number(m[2]) } : null;
}

function extOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot) : "";
}

/** Output filenames are `<content-hash><ext>` — show a readable head. */
function shortHash(filename: string): string {
  const dot = filename.lastIndexOf(".");
  const base = dot > 0 ? filename.slice(0, dot) : filename;
  const ext = dot > 0 ? filename.slice(dot) : "";
  return base.length > 14 ? `${base.slice(0, 10)}…${ext}` : filename;
}

/** Build log and output files of a finished run, grouped into run-level files
 * and paired expected/actual comparisons. Download links appear where storage
 * still has the file (GCS-backed runs get signed URLs). */
function ArtifactsSection({
  runId,
  samples,
}: Readonly<{
  runId: number;
  samples: RunFailure[];
}>) {
  const { data: artifacts = [], isLoading } = useRunArtifacts(runId);
  const [showAll, setShowAll] = useState(false);
  const [showOutputs, setShowOutputs] = useState(false);
  const [diff, setDiff] = useState<DiffTarget | null>(null);

  const { runFiles, comparisons } = useMemo(() => {
    const runFiles = RUN_FILE_TYPES.map((t) =>
      artifacts.find((a) => a.type === t),
    ).filter((a): a is RunArtifact => a != null);

    const groups = new Map<string, OutputComparison>();
    for (const a of artifacts) {
      if (a.type !== "expected_output" && a.type !== "actual_output") continue;
      const p = parseOutputKey(a.artifact_id);
      const key = p ? `${p.rtId}_${p.outputId}` : a.artifact_id;
      let g = groups.get(key);
      if (!g) {
        g = {
          key,
          rtId: p?.rtId ?? -1,
          outputId: p?.outputId ?? -1,
          ext: extOf(a.filename),
          expected: [],
          actual: null,
        };
        groups.set(key, g);
      }
      if (a.type === "expected_output") g.expected.push(a);
      else g.actual = a;
    }
    return { runFiles, comparisons: [...groups.values()] };
  }, [artifacts]);

  const samplesByRt = useMemo(() => {
    const m = new Map<number, RunFailure>();
    for (const s of samples) m.set(s.regression_test_id, s);
    return m;
  }, [samples]);

  if (!isLoading && artifacts.length === 0) return null;

  const visible = showAll ? comparisons : comparisons.slice(0, 6);

  return (
    <div className="mb-8">
      <h2 className="mb-1 text-[15px] font-semibold tracking-tight">Artifacts</h2>
      <p className="mb-3 text-[13px] text-faint">
        Files this run produced — build log and expected vs actual outputs.
      </p>
      {isLoading && (
        <div className="flex items-center gap-2 text-xs text-faint">
          <Loader2 className="size-3 animate-spin" /> loading artifact list
        </div>
      )}

      {runFiles.length > 0 && (
        <div>
          <SubLabel>Run files</SubLabel>
          <div className="grid gap-2 sm:grid-cols-2">
            {runFiles.map((a) => (
              <RunFileCard key={a.artifact_id} a={a} />
            ))}
          </div>
        </div>
      )}

      {comparisons.length > 0 && (
        <div className="mt-4">
          {/* Collapsed by default: a full run carries hundreds of these, and
              expanding them all buries the run files above. */}
          <button
            onClick={() => setShowOutputs(!showOutputs)}
            aria-expanded={showOutputs}
            className="mb-2 flex cursor-pointer items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-faint transition-colors hover:text-foreground"
          >
            <ChevronDown
              className={cn("size-3 transition-transform", !showOutputs && "-rotate-90")}
            />
            Output comparisons · {comparisons.length}
          </button>
          {showOutputs && (
          <>
          <div className="flex flex-col gap-2">
            {visible.map((cmp) => {
              const sample = samplesByRt.get(cmp.rtId);
              return (
                <ComparisonCard
                  key={cmp.key}
                  cmp={cmp}
                  sample={sample}
                  onDiff={
                    sample
                      ? () =>
                          setDiff({
                            runId,
                            sampleId: sample.sample_id,
                            regressionId: cmp.rtId,
                            outputId: cmp.outputId,
                            command: sample.command,
                            sampleName: sample.sample_name,
                          })
                      : undefined
                  }
                />
              );
            })}
          </div>
          {comparisons.length > 6 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="mt-1.5 cursor-pointer text-[11px] text-faint hover:text-foreground"
            >
              {showAll ? "show fewer" : `show all ${comparisons.length}`}
            </button>
          )}
          </>
          )}
        </div>
      )}

      <DiffDrawer target={diff} onClose={() => setDiff(null)} />
    </div>
  );
}

function SubLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-faint">
      {children}
    </div>
  );
}

/** Availability of one artifact file: a download link, on-server, or missing. */
function FileStatus({ a, compact }: Readonly<{ a: RunArtifact; compact?: boolean }>) {
  const url = httpsUrl(a.download_url);
  if (url) {
    return (
      <a
        href={url}
        download={a.filename}
        className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-primary hover:underline"
      >
        <Download className="size-3" />
        {!compact && "Download"}
      </a>
    );
  }
  const ok = a.storage_status === "ok";
  return (
    <span className={cn("shrink-0 text-[11px]", ok ? "text-faint" : "text-faint/60")}>
      {ok ? "On server" : "Missing"}
    </span>
  );
}

/**
 * Build-log download. The artifacts endpoint reports the log with a null
 * download_url because it is read through /runs/{id}/logs instead of being
 * served as a file, so the log is paged in and saved from a blob here rather
 * than linked to.
 */
/** Download button wording for each of its three states. */
function logLabel(busy: boolean, failed: boolean): string {
  if (busy) return "Preparing";
  return failed ? "Retry" : "Download";
}

function LogDownload({ runId, filename }: Readonly<{ runId: number; filename: string }>) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const save = async () => {
    setBusy(true);
    setFailed(false);
    try {
      const blob = new Blob([await fetchRunLog(runId)], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={save}
      disabled={busy}
      className="flex shrink-0 cursor-pointer items-center gap-1 text-[11px] font-medium text-primary hover:underline disabled:cursor-default disabled:opacity-60"
    >
      {busy ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
      {logLabel(busy, failed)}
    </button>
  );
}

function RunFileCard({ a }: Readonly<{ a: RunArtifact }>) {
  const Icon = RUN_FILE_ICON[a.type] ?? FileText;
  const viaLogEndpoint =
    a.type === "build_log" && a.storage_status === "ok" && !httpsUrl(a.download_url);
  return (
    <div className="flex items-center gap-2.5 rounded-lg border bg-card px-3 py-2 shadow-card">
      <Icon className="size-4 shrink-0 text-faint" />
      <div className="min-w-0 flex-1">
        <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {RUN_FILE_LABEL[a.type] ?? a.type.replaceAll("_", " ")}
        </div>
        <code className="block truncate text-[12px]" title={a.filename}>
          {a.filename}
        </code>
      </div>
      {a.size_bytes != null && (
        <span className="shrink-0 tabular-nums text-[11px] text-faint">
          {(a.size_bytes / 1024).toFixed(0)} KB
        </span>
      )}
      {viaLogEndpoint ? (
        <LogDownload runId={a.run_id} filename={a.filename} />
      ) : (
        <FileStatus a={a} />
      )}
    </div>
  );
}

type CompareTone = "match" | "differs" | "noout";

function StatusPill({ tone }: Readonly<{ tone: CompareTone }>) {
  const map: Record<CompareTone, [string, string]> = {
    match: ["Match", "text-success bg-success/10"],
    differs: ["Differs", "text-destructive bg-destructive/10"],
    noout: ["No output", "text-warning bg-warning/10"],
  };
  const [label, cls] = map[tone];
  return (
    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium", cls)}>
      {label}
    </span>
  );
}

function OutputCol({
  title,
  files,
  empty,
}: Readonly<{
  title: string;
  files: RunArtifact[];
  empty?: string;
}>) {
  return (
    <div className="min-w-0 px-3.5 py-2">
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-faint">
        {title}
      </div>
      {files.length === 0 ? (
        <span className="text-[11px] italic text-faint">{empty ?? "—"}</span>
      ) : (
        files.map((f, i) => (
          <div key={f.artifact_id} className="flex items-center gap-2 py-0.5">
            {files.length > 1 && (
              <span className="shrink-0 text-[9px] text-faint">v{i + 1}</span>
            )}
            <code className="min-w-0 flex-1 truncate text-[11.5px]" title={f.filename}>
              {shortHash(f.filename)}
            </code>
            <FileStatus a={f} compact />
          </div>
        ))
      )}
    </div>
  );
}

/** No output at all, a match, or a genuine difference. */
function toneOf(hasActual: boolean, matches: boolean): CompareTone {
  if (!hasActual) return "noout";
  return matches ? "match" : "differs";
}

function ComparisonCard({
  cmp,
  sample,
  onDiff,
}: Readonly<{
  cmp: OutputComparison;
  sample: RunFailure | undefined;
  onDiff?: () => void;
}>) {
  const label = sample?.sample_name ?? `Test #${cmp.rtId}`;
  const outStatus = sample?.outputs.find((o) => o.output_id === cmp.outputId)?.status;
  const matched =
    cmp.actual != null &&
    cmp.expected.some((e) => e.filename === cmp.actual!.filename);
  const tone: CompareTone = toneOf(cmp.actual != null, outStatus === "pass" || matched);

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-card">
      <div className="flex items-center gap-2 border-b px-3.5 py-2">
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium" title={label}>
          {label}
        </span>
        {cmp.ext && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {cmp.ext}
          </span>
        )}
        <StatusPill tone={tone} />
      </div>
      {sample?.command && (
        <code
          className="block truncate border-b px-3.5 py-1.5 text-[11px] text-faint"
          title={sample.command}
        >
          #{cmp.rtId} · {sample.command}
        </code>
      )}
      <div className="grid grid-cols-2 divide-x">
        <OutputCol title="Expected" files={cmp.expected} />
        <OutputCol
          title="Actual"
          files={cmp.actual ? [cmp.actual] : []}
          empty="no output produced"
        />
      </div>
      {onDiff && cmp.actual && tone === "differs" && (
        <div className="border-t px-3.5 py-1.5 text-right">
          <button
            onClick={onDiff}
            className="cursor-pointer text-[11px] font-medium text-primary hover:underline"
          >
            View diff
          </button>
        </div>
      )}
    </div>
  );
}

function MetaRow({
  label, children, last,
}: Readonly<{
  label: string;
  children: React.ReactNode;
  last?: boolean;
}>) {
  return (
    <div className={cn("grid grid-cols-[150px_1fr] items-center bg-card", !last && "border-b")}>
      <div className="bg-muted/40 px-3 py-2 text-[12px] font-medium text-muted-foreground">
        {label}
      </div>
      <div className="px-3 py-2 text-[13px]">{children}</div>
    </div>
  );
}

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
