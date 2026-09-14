import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { Copy, Download, FileVideo, FlaskConical, Loader2, Lock, Plus, Search, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";

import { Sparkline } from "@/components/Sparkline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import {
  baselineFile,
  categoryHealth,
  createVariant,
  deleteVariant,
  deriveCategories,
  healthOf,
  updateRegressionTest,
  useRegressionTestDetail,
  useRegressionTests,
  useSampleHistory,
  variantFile,
  type StoredFile,
} from "@/lib/api";
import { useResizableWidth } from "@/components/ResizeHandle";
import { canManage, getSession } from "@/lib/auth";
import type { Platform, RegressionTest, SparkResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { COMMAND_MAX } from "@/lib/validate";

/**
 * Regression tests: category rail, test list, detail panel. Baselines are
 * fetched per test rather than with the list, which is how the API splits
 * them: outputs multiply the payload for every row. Editing needs admin or
 * contributor.
 */
export function Workspace() {
  const { data: tests = [], isLoading } = useRegressionTests();
  const search = useSearch({ from: "/tests" }) as { t?: number };
  const navigate = useNavigate();
  const selected = tests.find((t) => t.id === search.t) ?? null;

  const rail = useResizableWidth("rail", 208, 160, 320);
  const listPane = useResizableWidth("list", 360, 280, 640);

  const [cat, setCat] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [onlyFailing, setOnlyFailing] = useState(false);

  const list = useMemo(() => {
    let l = tests;
    if (cat) l = l.filter((t) => t.categories.includes(cat));
    if (onlyFailing) l = l.filter((t) => healthOf(t) === "fail");
    if (q) {
      const needle = q.toLowerCase();
      l = l.filter((t) =>
        `#${t.id} ${t.command} ${t.sample_name} ${t.description}`.toLowerCase().includes(needle),
      );
    }
    return l;
  }, [tests, cat, q, onlyFailing]);

  const select = (id: number) => navigate({ to: "/tests", search: { t: id } });

  return (
    <div className="flex h-full">
      {/* Category rail */}
      <div className="flex shrink-0 flex-col border-r" style={{ width: rail.width }}>
        <div className="px-3 py-3 text-[11px] font-semibold uppercase tracking-wider text-faint">
          Categories
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          <RailItem
            label="All tests"
            count={tests.length}
            failing={tests.filter((t) => healthOf(t) === "fail").length}
            active={cat === null}
            onClick={() => setCat(null)}
          />
          {deriveCategories(tests)
            .filter((c) => c.test_count > 0)
            .map((c) => {
              const h = categoryHealth(c.name, tests);
              return (
                <RailItem
                  key={c.id}
                  label={c.name}
                  count={h.total}
                  failing={h.failing}
                  active={cat === c.name}
                  onClick={() => setCat(c.name)}
                />
              );
            })}
        </div>
      </div>
      {rail.handle}

      {/* Test list */}
      <div className="flex shrink-0 flex-col border-r" style={{ width: listPane.width }}>
        <div className="flex items-center gap-2 border-b px-3 py-2.5">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2 size-3.5 text-faint" />
            <Input
              placeholder={`Filter ${cat ?? "all"}…`}
              className="h-7 pl-8 text-xs"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <button
            onClick={() => setOnlyFailing(!onlyFailing)}
            className={cn(
              "cursor-pointer rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
              onlyFailing
                ? "border-destructive/40 bg-destructive/10 text-destructive"
                : "text-faint hover:bg-muted",
            )}
          >
            failing
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="flex flex-col gap-1 p-2">
              {Array.from({ length: 6 }, (_, n) => `placeholder-${n}`).map((id) => (
                <div key={id} className="h-11 animate-pulse rounded-lg bg-muted/60" />
              ))}
            </div>
          )}
          {list.map((t) => {
            const health = healthOf(t);
            return (
              <button
                key={t.id}
                onClick={() => select(t.id)}
                className={cn(
                  "flex w-full cursor-pointer flex-col gap-1 border-b px-3 py-2.5 text-left transition-colors",
                  selected?.id === t.id ? "bg-accent/60" : "hover:bg-muted/60",
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "size-1.5 shrink-0 rounded-full",
                      health === "pass" && "bg-success",
                      health === "fail" && "bg-destructive",
                      health === "skip" && "bg-faint",
                    )}
                  />
                  <code className="text-[11px] text-faint">#{t.id}</code>
                  <code className="min-w-0 flex-1 truncate text-xs text-foreground/90">
                    {t.command}
                  </code>
                  {!t.active && <Badge variant="secondary" className="shrink-0">off</Badge>}
                </div>
                <div className="flex items-center gap-2 pl-3.5">
                  <span className="min-w-0 flex-1 truncate text-[11px] text-faint">
                    {t.sample_name}
                  </span>
                  <Sparkline results={t.recent_results.filter((r) => r !== "skip").slice(-12)} />
                </div>
              </button>
            );
          })}
          {!isLoading && list.length === 0 && (
            <div className="px-3 py-12 text-center text-xs text-faint">No tests match.</div>
          )}
        </div>
        <div className="border-t px-3 py-2 text-[11px] text-faint">
          {list.length} of {tests.length} tests
        </div>
      </div>
      {listPane.handle}

      {/* Detail */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        {selected ? (
          <Detail key={selected.id} test={selected} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <FlaskConical className="size-8 text-faint" />
            <div className="text-[13px] text-faint">Select a test to see everything about it.</div>
          </div>
        )}
      </div>
    </div>
  );
}

function RailItem({
  label, count, failing, active, onClick,
}: Readonly<{
  label: string; count: number; failing: number; active: boolean; onClick: () => void;
}>) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors",
        active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60",
      )}
    >
      <span className="truncate">{label}</span>
      {failing > 0 && (
        <span className="ml-auto flex items-center gap-1 text-[11px] font-medium text-destructive">
          <span className="size-1.5 rounded-full bg-destructive" />
          {failing}
        </span>
      )}
      <span className={cn("tabular-nums text-[11px] text-faint", failing > 0 ? "" : "ml-auto")}>
        {count}
      </span>
    </button>
  );
}

/** How a test's most recent non-skipped result reads in words. */
function healthLabel(health: SparkResult): string {
  if (health === "pass") return "passing";
  return health === "fail" ? "failing" : "not run recently";
}

function Detail({ test }: Readonly<{ test: RegressionTest }>) {
  const editable = canManage(getSession());
  const qc = useQueryClient();
  const { data: history = [] } = useSampleHistory(test.sample_id);
  const { data: detail } = useRegressionTestDetail(test.id);
  const outputs = detail?.outputs ?? [];
  const [command, setCommand] = useState(test.command);
  const [description, setDescription] = useState(test.description);
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty = command !== test.command || description !== test.description;
  const health = healthOf(test);

  // Every actual run of THIS test (both platforms), newest first.
  const testRuns = history
    .filter((h) => h.regression_test_id === test.id)
    .sort((a, b) => b.run_id - a.run_id);

  // Live sparkline: only runs where the test actually executed — no skips.
  // pass = green, anything else (fail/missing/error) = red.
  const liveResults: SparkResult[] = testRuns
    .slice(0, 20)
    .reverse()
    .map((h) => (h.status === "pass" ? "pass" : "fail"));
  const passN = liveResults.filter((r) => r === "pass").length;

  const byPlatform = testRuns.reduce<Record<Platform, typeof history>>(
    (acc, h) => {
      const platform = h.platform as Platform;
      acc[platform] ??= [];
      acc[platform].push(h);
      return acc;
    },
    { linux: [], windows: [] },
  );

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await updateRegressionTest(test.id, { command, description });
      await qc.invalidateQueries({ queryKey: ["regression-tests"] });
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async () => {
    setToggling(true);
    try {
      await updateRegressionTest(test.id, { active: !test.active });
      await qc.invalidateQueries({ queryKey: ["regression-tests"] });
    } finally {
      setToggling(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="flex min-h-full flex-col"
    >
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h2 className="text-[15px] font-semibold tracking-tight">Test #{test.id}</h2>
          <span
            className={cn(
              "flex items-center gap-1.5 text-xs font-medium",
              health === "pass" && "text-success",
              health === "fail" && "text-destructive",
              health === "skip" && "text-faint",
            )}
          >
            <span className="size-2 rounded-full bg-current" />
            {healthLabel(health)}
          </span>
          {test.categories.map((c) => (
            <Badge key={c} variant="secondary">{c}</Badge>
          ))}
          <div className="ml-auto flex items-center gap-2">
            {saveError && <span className="text-[11px] text-destructive">{saveError}</span>}
            {editable ? (
              <>
                <Button size="sm" variant="outline" disabled={toggling} onClick={toggleActive}>
                  {toggling && <Loader2 className="animate-spin" />}
                  {test.active ? "Deactivate" : "Activate"}
                </Button>
                <Button size="sm" disabled={!dirty || saving} onClick={save}>
                  {saving && <Loader2 className="animate-spin" />} Save
                </Button>
              </>
            ) : (
              <span className="flex items-center gap-1.5 text-[11px] text-faint">
                <Lock className="size-3" /> read-only — changes are admin-only
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-6 px-6 py-5">
        <section className="flex items-center gap-3 rounded-xl border bg-muted/30 p-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <FileVideo className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{test.sample_name}</div>
            <code className="text-[11px] text-faint">
              {test.sample_sha ? `${test.sample_sha.slice(0, 24)}… · ` : ""}
              {test.input_type} → {test.output_type}
            </code>
          </div>
        </section>

        <section>
          <SectionLabel>Command</SectionLabel>
          <div className="overflow-hidden rounded-xl border shadow-card">
            <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5">
              <span className="font-mono text-[11px] text-faint">ccextractor &lt;sample&gt; …</span>
              <button
                className="ml-auto cursor-pointer rounded p-1 text-faint transition-colors hover:bg-muted hover:text-foreground"
                title="Copy local repro command"
                onClick={() =>
                  navigator.clipboard.writeText(`ccextractor ${test.sample_name} ${test.command}`)
                }
              >
                <Copy className="size-3" />
              </button>
            </div>
            <Textarea
              className="rounded-none border-0 font-mono text-xs shadow-none focus-visible:ring-0"
              value={command}
              readOnly={!editable}
              maxLength={COMMAND_MAX}
              onChange={(e) => setCommand(e.target.value)}
            />
          </div>
          {editable && (
            <div className="mt-1 text-[11px] text-warning">
              This command runs verbatim on the CI VMs for every future run.
            </div>
          )}
          <div className="mt-1.5 flex gap-4 text-[11px] text-faint">
            <span>expected RC <b className="text-muted-foreground">{test.expected_rc}</b></span>
            {test.avg_runtime_ms != null && (
              <span>
                avg runtime{" "}
                <b className="text-muted-foreground">{(test.avg_runtime_ms / 1000).toFixed(1)}s</b>
              </span>
            )}
            <span>
              status{" "}
              <b className={test.active ? "text-success" : "text-warning"}>
                {test.active ? "active" : "inactive"}
              </b>
            </span>
          </div>
        </section>

        <section>
          <SectionLabel>History — last {liveResults.length || "0"} runs of this test</SectionLabel>
          {liveResults.length > 0 ? (
            <div className="flex items-center gap-4 rounded-xl border bg-muted/30 p-3.5">
              <Sparkline results={liveResults} className="gap-1 [&>span]:w-2" />
              <span className="text-[11px] text-faint">
                {passN} pass · {liveResults.length - passN} fail · runs that included this test
              </span>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed p-3 text-center text-xs text-faint">
              This test hasn't run in any recorded run yet.
            </div>
          )}
        </section>

        <section>
          <SectionLabel>Per-platform results — live</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            {(["linux", "windows"] as Platform[]).map((p) => {
              const rows = byPlatform[p] ?? [];
              return (
                <div key={p} className="rounded-xl border bg-card p-3 shadow-card">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-faint">
                    {p}
                  </div>
                  {rows.length === 0 ? (
                    <div className="text-[12px] text-faint">no results</div>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {rows.slice(0, 6).map((h) => (
                        <Link
                          key={`${h.run_id}-${h.regression_test_id}`}
                          to="/runs/$runId"
                          params={{ runId: String(h.run_id) }}
                          className="flex items-center gap-2 text-[12px] transition-colors hover:text-foreground"
                          title={`run ${h.run_id} · ${h.commit_sha.slice(0, 9)}`}
                        >
                          <span
                            className={cn(
                              "size-1.5 shrink-0 rounded-full",
                              h.status === "pass" && "bg-success",
                              h.status === "fail" && "bg-destructive",
                              h.status !== "pass" && h.status !== "fail" && "bg-warning",
                            )}
                          />
                          <code className="text-faint">run {h.run_id}</code>
                          <span
                            className={cn(
                              "ml-auto",
                              h.status === "pass" && "text-success",
                              h.status === "fail" && "text-destructive",
                              h.status !== "pass" && h.status !== "fail" && "text-warning",
                            )}
                          >
                            {h.status}
                          </span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {outputs.length > 0 && (
          <section>
            <SectionLabel>Baselines</SectionLabel>
            <div className="flex flex-col gap-2">
              {outputs.map((o) => (
                <div key={o.id} className="rounded-xl border p-3 shadow-card">
                  <div className="flex items-center gap-2">
                    <Badge variant="accent">original</Badge>
                    <code className="text-xs">
                      {o.correct.slice(0, 28)}…{o.correct_extension}
                    </code>
                    {o.ignore && <Badge variant="secondary">ignored</Badge>}
                    <DownloadFile
                      className="ml-auto"
                      locate={() => baselineFile(test.id, o.id)}
                    />
                  </div>
                  {o.variants.map((v, i) => (
                    <div key={v.id} className="mt-2 flex items-center gap-2 border-t pt-2">
                      <Badge variant="secondary">variant {i + 1}</Badge>
                      <code className="text-xs text-muted-foreground">
                        {v.hash.slice(0, 28)}…
                      </code>
                      <DownloadFile
                        className="ml-auto"
                        locate={() => variantFile(test.id, o.id, v.id)}
                      />
                      {editable && (
                        <RemoveVariant testId={test.id} outputId={o.id} variantId={v.id} />
                      )}
                    </div>
                  ))}
                  {editable && <AddVariant testId={test.id} outputId={o.id} />}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="pb-6">
          <SectionLabel>Description</SectionLabel>
          <Textarea
            value={description}
            readOnly={!editable}
            placeholder={editable ? "Why does this test exist?" : "—"}
            onChange={(e) => setDescription(e.target.value)}
          />
        </section>
      </div>
    </motion.div>
  );
}

/**
 * Accept one more output hash for a baseline.
 *
 * A test can legitimately produce different bytes on a different platform or
 * CCExtractor build. Recording that hash lets those runs pass without moving
 * the baseline everyone else is compared against.
 */
function AddVariant({ testId, outputId }: Readonly<{ testId: number; outputId: number }>) {
  const qc = useQueryClient();
  const [hash, setHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      await createVariant(testId, outputId, hash);
      await qc.invalidateQueries({ queryKey: ["regression-test", testId] });
      setHash("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 border-t pt-2">
      <div className="flex items-center gap-2">
        {/* The hash is joined to the baseline's extension to name a file on
            disk, so the API only accepts letters and digits. */}
        <input
          value={hash}
          onChange={(e) => setHash(e.target.value.replace(/[^a-z0-9]/gi, ""))}
          placeholder="accept another output hash"
          className="h-7 flex-1 rounded-md border bg-card px-2 font-mono text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button size="sm" variant="secondary" disabled={busy || !hash} onClick={add}>
          {busy ? <Loader2 className="animate-spin" /> : <Plus />} Add variant
        </Button>
      </div>
      {error && <div className="mt-1 text-[11px] text-destructive">{error}</div>}
    </div>
  );
}

function RemoveVariant({
  testId,
  outputId,
  variantId,
}: Readonly<{
  testId: number;
  outputId: number;
  variantId: number;
}>) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    try {
      await deleteVariant(testId, outputId, variantId);
      await qc.invalidateQueries({ queryKey: ["regression-test", testId] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-destructive"
      title="Stop accepting this output"
      disabled={busy}
      onClick={go}
    >
      {busy ? <Loader2 className="animate-spin" /> : <Trash2 />}
    </Button>
  );
}

/**
 * Download button for a file the API locates rather than serves.
 *
 * The endpoint answers with a signed URL, so the click has to resolve that
 * first and then follow it. When the only copy is on the platform's own disk
 * there is no URL to follow, which the button reports rather than failing
 * silently.
 */
function DownloadFile({
  locate,
  className,
}: Readonly<{
  locate: () => Promise<StoredFile>;
  className?: string;
}>) {
  const [state, setState] = useState<"idle" | "busy" | "unavailable">("idle");

  const go = async () => {
    setState("busy");
    try {
      const file = await locate();
      if (!file.download_url) {
        setState("unavailable");
        return;
      }
      window.open(file.download_url, "_blank", "noopener");
      setState("idle");
    } catch {
      setState("unavailable");
    }
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      className={className}
      disabled={state === "busy"}
      onClick={go}
    >
      {state === "busy" ? <Loader2 className="animate-spin" /> : <Download />}
      {state === "unavailable" ? "on server only" : "download"}
    </Button>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}
