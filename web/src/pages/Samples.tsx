import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, Download, FileVideo, Loader2, Search, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm";
import { Input } from "@/components/ui/input";
import { AnimatedSheet, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { getSession } from "@/lib/auth";
import {
  deleteExtraFile,
  deleteSample,
  extraFile,
  mediaInfoFile,
  sampleFile,
  updateSample,
  useTags,
  type StoredFile,
  useRegressionTests,
  useSampleDetails,
  useSampleHistory,
  useSamples,
  type MediaInfoNode,
} from "@/lib/api";
import type { Platform, Sample } from "@/lib/types";
import { cn } from "@/lib/utils";

/** "Samples" — live from GET /api/v1/samples. */
export function Samples() {
  const { data: samples = [], isLoading } = useSamples();
  const { data: tests = [] } = useRegressionTests();
  const [q, setQ] = useState("");
  const [ext, setExt] = useState<string | null>(null);
  const [selected, setSelected] = useState<Sample | null>(null);
  const [limit, setLimit] = useState(60);

  const extensions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of samples) counts.set(s.extension, (counts.get(s.extension) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [samples]);

  const filtered = useMemo(
    () =>
      samples.filter((s) => {
        if (ext && s.extension !== ext) return false;
        if (
          q &&
          !`${s.original_name} ${s.sha} ${s.tags.join(" ")}`.toLowerCase().includes(q.toLowerCase())
        )
          return false;
        return true;
      }),
    [samples, q, ext],
  );

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Samples</h1>
          <span className="text-xs text-faint">{samples.length} media samples</span>
          <div className="relative ml-auto">
            <Search className="absolute left-2.5 top-2 size-3.5 text-faint" />
            <Input
              placeholder="Name, sha, tag…"
              className="h-7 w-64 pl-8 text-xs"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="px-6 py-4">
        <div className="mb-4 flex flex-wrap gap-1">
          {extensions.slice(0, 18).map(([e, count]) => (
            <button
              key={e}
              onClick={() => setExt(ext === e ? null : e)}
              className={cn(
                "cursor-pointer rounded-md border px-2 py-0.5 font-mono text-[11px] transition-colors",
                ext === e
                  ? "border-primary/40 bg-accent text-accent-foreground"
                  : "border-transparent text-faint hover:border-border hover:text-muted-foreground",
              )}
            >
              {e} <span className="opacity-60">{count}</span>
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 9 }, (_, n) => `placeholder-${n}`).map((id) => (
              <div key={id} className="h-24 animate-pulse rounded-xl border bg-muted/50" />
            ))}
          </div>
        )}

        <div className="grid grid-cols-3 gap-3">
          {filtered.slice(0, limit).map((s, i) => {
            const sampleTests = tests.filter((t) => t.sample_id === s.id);
            return (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.015, 0.3), duration: 0.2 }}
                onClick={() => setSelected(s)}
                className="card-hover cursor-pointer rounded-xl border bg-card p-3.5 shadow-card"
              >
                <div className="flex items-start gap-2.5">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <FileVideo className="size-3.5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium" title={s.original_name}>
                      {s.original_name}
                    </div>
                    <code className="text-[10px] text-faint">{s.sha.slice(0, 20)}…</code>
                  </div>
                  <Badge variant="secondary" className="font-mono">{s.extension}</Badge>
                </div>
                <div className="mt-2.5 flex items-center gap-1.5">
                  {s.tags.slice(0, 3).map((t) => (
                    <Badge key={t} variant="outline">{t}</Badge>
                  ))}
                  <span className="ml-auto text-[11px] text-faint">
                    {sampleTests.length > 0 ? (
                      <Link
                        to="/tests"
                        search={{ t: sampleTests[0].id }}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium text-primary hover:underline"
                      >
                        {sampleTests.length} test{sampleTests.length > 1 ? "s" : ""} →
                      </Link>
                    ) : (
                      <span className="text-warning">no tests</span>
                    )}
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
        {filtered.length > limit && (
          <div className="py-4 text-center">
            <button
              onClick={() => setLimit(limit + 60)}
              className="cursor-pointer rounded-lg border px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:bg-muted"
            >
              Show 60 more · {filtered.length - limit} remaining
            </button>
          </div>
        )}
      </div>

      <AnimatedSheet
        open={!!selected}
        onOpenChange={(o) => !o && setSelected(null)}
        resizeKey="sample-detail"
      >
        {selected && <SampleDetail sample={selected} />}
      </AnimatedSheet>
    </div>
  );
}

/**
 * Full sample-info drawer: basic details,
 * upload metadata, tags, per-platform test status, tests, media-info tree,
 * and cross-run result history. Everything live.
 */
function SampleDetail({ sample }: Readonly<{ sample: Sample }>) {
  const { data: details } = useSampleDetails(sample.id);
  const { data: history = [], isLoading } = useSampleHistory(sample.id);
  const { data: tests = [] } = useRegressionTests();
  const sampleTests = tests.filter((t) => t.sample_id === sample.id);
  const upload = details?.upload;
  const admin = getSession()?.role === "admin";

  // Latest result per platform → the "test status" summary the old page had.
  const perPlatform = useMemo(() => {
    const out: Record<Platform, { status: string; run_id: number } | null> = {
      linux: null,
      windows: null,
    };
    for (const h of history) {
      const p = h.platform as Platform;
      out[p] ??= { status: h.status, run_id: h.run_id };
    }
    return out;
  }, [history]);

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b px-6 py-4">
        <SheetTitle className="truncate pr-8 text-[15px] font-semibold tracking-tight">
          {sample.original_name}
        </SheetTitle>
        <div className="mt-0.5 flex items-center gap-2">
          <SheetDescription className="text-[11px] text-faint">
            Sample #{sample.id} · {sample.extension}
          </SheetDescription>
          <SampleDownload sampleId={sample.id} />
        </div>
      </div>

      <div className="flex flex-col gap-5 px-6 py-5">
        <section>
          <SectionLabel>Basic details</SectionLabel>
          <dl className="rounded-xl border bg-muted/30 p-3.5 text-[12px]">
            <Row label="SHA-256">
              <div className="flex items-center gap-1.5">
                <code className="break-all">{sample.sha}</code>
                <button
                  className="shrink-0 cursor-pointer rounded p-0.5 text-faint hover:text-foreground"
                  onClick={() => navigator.clipboard.writeText(sample.sha)}
                  title="Copy SHA"
                >
                  <Copy className="size-3" />
                </button>
              </div>
            </Row>
            <Row label="Extension">{sample.extension}</Row>
            {upload && (
              <>
                <Row label="CCExtractor version">
                  {upload.version ?? "unknown"}
                  {upload.version_released && ` (released ${upload.version_released})`}
                </Row>
                <Row label="Platform">{upload.platform ?? "—"}</Row>
                <Row label="Parameters">
                  <code>{upload.parameters || "—"}</code>
                </Row>
                <Row label="Notes" last>{upload.notes || "—"}</Row>
              </>
            )}
          </dl>
          {admin ? (
            <TagEditor sample={sample} />
          ) : (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-faint">Tags:</span>
              {sample.tags.length ? (
                sample.tags.map((t) => <Badge key={t} variant="secondary">{t}</Badge>)
              ) : (
                <span className="text-[11px] text-faint">no tags yet</span>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-3 border-t pt-3">
            <FileLink label="media info" locate={() => mediaInfoFile(sample.id)} />
            {(details?.extra_files ?? []).map((x) => (
              <span key={x.id} className="flex items-center gap-1">
                <FileLink
                  label={x.original_name}
                  locate={() => extraFile(sample.id, x.id)}
                />
                {admin && <RemoveExtraFile sampleId={sample.id} extraId={x.id} />}
              </span>
            ))}
            {admin && <span className="ml-auto"><DeleteSample sample={sample} /></span>}
          </div>
        </section>

        <section>
          <SectionLabel>Test status</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            {(["linux", "windows"] as Platform[]).map((p) => {
              const r = perPlatform[p];
              return (
                <div key={p} className="rounded-xl border bg-card p-3 shadow-card">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-faint">
                    {p}
                  </div>
                  {r ? (
                    <Link
                      to="/runs/$runId"
                      params={{ runId: String(r.run_id) }}
                      className="flex items-center gap-1.5 text-[13px] font-medium hover:underline"
                    >
                      <span
                        className={cn(
                          "size-2 rounded-full",
                          r.status === "pass" && "bg-success",
                          r.status === "fail" && "bg-destructive",
                          r.status !== "pass" && r.status !== "fail" && "bg-warning",
                        )}
                      />
                      <span
                        className={cn(
                          r.status === "pass" && "text-success",
                          r.status === "fail" && "text-destructive",
                        )}
                      >
                        {r.status}
                      </span>
                      <span className="text-[11px] text-faint">· run {r.run_id}</span>
                    </Link>
                  ) : (
                    <span className="text-[13px] text-faint">no runs</span>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <section>
          <SectionLabel>Regression tests using this sample</SectionLabel>
          <div className="flex flex-col gap-1">
            {sampleTests.map((t) => (
              <Link
                key={t.id}
                to="/tests"
                search={{ t: t.id }}
                className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs transition-colors hover:border-border-strong"
              >
                <code className="text-faint">#{t.id}</code>
                <code className="min-w-0 flex-1 truncate">{t.command}</code>
              </Link>
            ))}
            {sampleTests.length === 0 && (
              <div className="rounded-lg border border-dashed p-3 text-center text-xs text-warning">
                No regression tests use this sample yet.
              </div>
            )}
          </div>
        </section>

        {details?.media_info && (
          <section>
            <SectionLabel>Media info</SectionLabel>
            <div className="rounded-xl border bg-muted/30 p-3.5 font-mono text-[11px] leading-relaxed">
              {details.media_info.map((node) => (
                <MediaNode key={node.name} node={node} />
              ))}
            </div>
          </section>
        )}

        <section>
          <SectionLabel>Result history — live</SectionLabel>
          {isLoading && <div className="h-24 animate-pulse rounded-lg bg-muted/60" />}
          <div className="flex flex-col">
            {history.map((h) => (
              <div
                key={`${h.run_id}-${h.regression_test_id}`}
                className="flex items-center gap-2.5 border-b py-1.5 text-xs last:border-0"
              >
                <span
                  className={cn(
                    "size-2 shrink-0 rounded-full",
                    h.status === "pass" && "bg-success",
                    h.status === "fail" && "bg-destructive",
                    h.status !== "pass" && h.status !== "fail" && "bg-faint",
                  )}
                />
                <span className="w-14 shrink-0 uppercase tracking-wider text-[10px] text-faint">
                  {h.platform}
                </span>
                <code className="text-faint">test #{h.regression_test_id}</code>
                <code className="min-w-0 flex-1 truncate text-faint">
                  {h.commit_sha.slice(0, 9)}
                </code>
                <span className="shrink-0 text-[10px] text-faint">
                  {h.tested_at && new Date(h.tested_at).toLocaleDateString()}
                </span>
              </div>
            ))}
            {!isLoading && history.length === 0 && (
              <div className="py-4 text-center text-xs text-faint">No recorded results.</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

/**
 * Resolves the sample's signed URL on click and follows it.
 *
 * Samples are gigabytes, so the API answers with a location instead of the
 * bytes. Where the only copy is on the platform's own disk there is no URL
 * to follow and the button says so.
 */
function SampleDownload({ sampleId }: Readonly<{ sampleId: number }>) {
  const [state, setState] = useState<"idle" | "busy" | "unavailable">("idle");

  const go = async () => {
    setState("busy");
    try {
      const file = await sampleFile(sampleId);
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
    <button
      onClick={go}
      disabled={state !== "idle"}
      className="flex cursor-pointer items-center gap-1 text-[11px] font-medium text-primary hover:underline disabled:cursor-default disabled:text-faint disabled:no-underline"
    >
      {state === "busy" ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <Download className="size-3" />
      )}
      {state === "unavailable" ? "on server only" : "download"}
    </button>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}

function Row({
  label, children, last,
}: Readonly<{
  label: string;
  children: React.ReactNode;
  last?: boolean;
}>) {
  return (
    <div className={cn("grid grid-cols-[130px_1fr] gap-2 py-1", !last && "border-b border-border/60")}>
      <dt className="text-faint">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** Renders one media-info node: a scalar, a flat dict, or a list of tracks. */
function MediaNode({ node, depth = 0 }: Readonly<{ node: MediaInfoNode; depth?: number }>) {
  const pad = { paddingLeft: depth * 12 };
  if (typeof node.value === "string") {
    return (
      <div style={pad}>
        <span className="text-faint">{node.name}:</span> {node.value}
      </div>
    );
  }
  if (Array.isArray(node.value)) {
    return (
      <div style={pad}>
        <div className="text-accent-foreground">{node.name}:</div>
        {node.value.map((track) => (
          <div key={track.name} style={{ paddingLeft: (depth + 1) * 12 }}>
            <div className="text-faint">{track.name}:</div>
            {Object.entries(track.value).map(([k, v]) => (
              <div key={k} style={{ paddingLeft: (depth + 2) * 12 }}>
                <span className="text-faint">{k}:</span> {v}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div style={pad}>
      <div className="text-accent-foreground">{node.name}:</div>
      {Object.entries(node.value).map(([k, v]) => (
        <div key={k} style={{ paddingLeft: (depth + 1) * 12 }}>
          <span className="text-faint">{k}:</span> {v}
        </div>
      ))}
    </div>
  );
}

/**
 * Tag editing for one sample.
 *
 * Tags are picked from the platform's list rather than typed, because the
 * API matches them by name and a typo would just be rejected. Creating a
 * new tag is an admin action of its own, on the administration page.
 */
function TagEditor({ sample }: Readonly<{ sample: Sample }>) {
  const qc = useQueryClient();
  const { data: tags = [] } = useTags();
  const [chosen, setChosen] = useState<string[]>(sample.tags);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    chosen.length !== sample.tags.length ||
    chosen.some((t) => !sample.tags.includes(t));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updateSample(sample.id, { tags: chosen });
      await qc.invalidateQueries({ queryKey: ["samples"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] text-faint">Tags:</span>
      {tags.map((t) => {
        const on = chosen.includes(t.name);
        return (
          <button
            key={t.id}
            title={t.description}
            onClick={() =>
              setChosen(on ? chosen.filter((c) => c !== t.name) : [...chosen, t.name])
            }
            className={cn(
              "cursor-pointer rounded-md border px-2 py-0.5 text-[11px] transition-colors",
              on
                ? "border-primary/40 bg-accent text-accent-foreground"
                : "border-transparent text-faint hover:border-border hover:text-muted-foreground",
            )}
          >
            {t.name}
          </button>
        );
      })}
      {tags.length === 0 && (
        <span className="text-[11px] text-faint">no tags defined yet</span>
      )}
      {dirty && (
        <Button size="sm" variant="secondary" disabled={busy} onClick={save}>
          {busy ? <Loader2 className="animate-spin" /> : null} Save tags
        </Button>
      )}
      {error && <span className="text-[11px] text-destructive">{error}</span>}
    </div>
  );
}

/** Deletes a sample, refused by the API while any test still uses it. */
function DeleteSample({ sample }: Readonly<{ sample: Sample }>) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteSample(sample.id);
      await qc.invalidateQueries({ queryKey: ["samples"] });
      setConfirming(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive"
        onClick={() => setConfirming(true)}
      >
        <Trash2 /> Delete sample
      </Button>
      {error && <div className="mt-1 text-[11px] text-destructive">{error}</div>}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Delete ${sample.original_name}?`}
        body={
          <>
            The media file, its media info and any accompanying files are
            removed from the repository. <b>This cannot be undone.</b> The
            platform refuses while a regression test still uses the sample.
          </>
        }
        confirmLabel={busy ? "Deleting…" : "Delete sample"}
        busy={busy}
        onConfirm={go}
      />
    </>
  );
}

/**
 * Drops one of the files uploaded alongside a sample.
 *
 * No confirm dialog: unlike deleting the sample this loses a single
 * accompanying file, and the classic page removes it on one click too.
 */
function RemoveExtraFile({ sampleId, extraId }: Readonly<{ sampleId: number; extraId: number }>) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    try {
      await deleteExtraFile(sampleId, extraId);
      await qc.invalidateQueries({ queryKey: ["sample-details", sampleId] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={go}
      disabled={busy}
      title="Delete this file"
      className="cursor-pointer text-[11px] text-faint hover:text-destructive disabled:opacity-50"
    >
      {busy ? <Loader2 className="size-3 animate-spin" /> : "×"}
    </button>
  );
}

/** Resolves a signed URL on click, the same way the baseline buttons do. */
function FileLink({
  label,
  locate,
}: Readonly<{
  label: string;
  locate: () => Promise<StoredFile>;
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
    <button
      onClick={go}
      disabled={state === "busy"}
      className="flex cursor-pointer items-center gap-1 text-[11px] font-medium text-primary hover:underline disabled:cursor-default disabled:text-faint disabled:no-underline"
    >
      {state === "busy" ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <Download className="size-3" />
      )}
      {state === "unavailable" ? "on server only" : label}
    </button>
  );
}
