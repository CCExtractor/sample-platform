import { useQuery } from "@tanstack/react-query";
import { Download, FileText, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AnimatedSheet, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { fetchConsoleDiff, fetchDiff, outputText, sampleFile } from "@/lib/api";
import { clock, cuesToVtt, parseCues, type Cue } from "@/lib/cues";
import { diffRows, whole, wordDiff, type DiffRow, type Seg } from "@/lib/diff";
import { cn } from "@/lib/utils";

export interface OutputDiffTarget {
  kind?: "output";
  runId: number;
  sampleId: number;
  regressionId: number;
  outputId: number;
  command: string;
  sampleName: string;
}

export interface ConsoleDiffTarget {
  kind: "console";
  runId: number;
  against?: number;
}

export type DiffTarget = OutputDiffTarget | ConsoleDiffTarget;

function isConsole(target: DiffTarget): target is ConsoleDiffTarget {
  return target.kind === "console";
}

type View = "diff" | "playback";

/** MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED — nothing here can decode the file. */
const MEDIA_ERR_SRC_NOT_SUPPORTED = 4;

/**
 * One failing output, either as a unified diff or played back against the
 * sample it came from.
 *
 * Playback is the view for deciding whether a mismatch is a real regression or
 * a stale baseline: captions only mean something next to the picture they
 * describe. The diff stays the default, because most differences are obvious
 * without watching anything.
 */
export function DiffDrawer({
  target,
  onClose,
}: Readonly<{
  target: DiffTarget | null;
  onClose: () => void;
}>) {
  const [view, setView] = useState<View>("diff");

  return (
    <AnimatedSheet
      open={!!target}
      onOpenChange={(o) => !o && onClose()}
      className={view === "playback" ? "max-w-5xl" : "max-w-2xl"}
    >
      {target && (
        <div className="flex h-full flex-col">
          <div className="border-b px-6 py-4">
            <SheetTitle className="text-[15px] font-semibold tracking-tight">
              {isConsole(target) ? "Combined stdout" : `Test #${target.regressionId}`}
            </SheetTitle>
            <SheetDescription className="mt-0.5 truncate font-mono text-[11px] text-faint">
              {isConsole(target)
                ? `run ${target.runId} vs previous completed run on this platform`
                : `${target.command} · ${target.sampleName} · run ${target.runId}`}
            </SheetDescription>
            {!isConsole(target) && (
              <div className="mt-3 flex gap-1">
                <ViewTab
                  icon={FileText}
                  label="Diff"
                  on={view === "diff"}
                  go={() => setView("diff")}
                />
                <ViewTab
                  icon={PlayCircle}
                  label="Playback"
                  on={view === "playback"}
                  go={() => setView("playback")}
                />
              </div>
            )}
          </div>
          {isConsole(target) || view === "diff" ? (
            <DiffPane target={target} />
          ) : (
            <PlaybackPane target={target} />
          )}
        </div>
      )}
    </AnimatedSheet>
  );
}

function ViewTab({
  icon: Icon,
  label,
  on,
  go,
}: Readonly<{
  icon: typeof FileText;
  label: string;
  on: boolean;
  go: () => void;
}>) {
  return (
    <button
      onClick={go}
      className={cn(
        "flex cursor-pointer items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors",
        // Tinted rather than a grey fill: the dialog puts a focus ring on the
        // first tab when it opens, and a grey fill reads as the same thing.
        on ? "bg-primary/10 text-primary" : "text-faint hover:text-foreground",
      )}
    >
      <Icon className="size-3.5" /> {label}
    </button>
  );
}

const ROW_TONE: Record<DiffRow["kind"], string> = {
  del: "bg-destructive/8 text-destructive",
  add: "bg-success/8 text-success",
  hunk: "text-accent-foreground",
  ctx: "",
};
const ROW_SIGN: Record<DiffRow["kind"], string> = { del: "−", add: "+", hunk: "", ctx: "" };
const MARK_TONE: Record<"del" | "add", string> = {
  del: "bg-destructive/35 text-foreground",
  add: "bg-success/35 text-foreground",
};

/** A line's segments, with the tokens that differ from its twin marked. */
function Segs({ segs, kind }: Readonly<{ segs: Seg[]; kind: "del" | "add" }>) {
  return (
    <>
      {segs.map((s) =>
        s.changed ? (
          <mark key={s.at} className={cn("rounded-sm", MARK_TONE[kind])}>
            {s.text}
          </mark>
        ) : (
          <span key={s.at}>{s.text}</span>
        ),
      )}
    </>
  );
}

function DiffPane({ target }: Readonly<{ target: DiffTarget }>) {
  const consoleTarget = isConsole(target);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: consoleTarget
      ? ["console-diff", target.runId, target.against ?? null]
      : ["diff", target.runId, target.regressionId, target.outputId],
    staleTime: Infinity,
    retry: false,
    queryFn: () => {
      if (isConsole(target)) {
        return fetchConsoleDiff(target.runId, target.against);
      }
      return fetchDiff(target);
    },
  });
  const rows = useMemo(() => (data ? diffRows(data.content) : []), [data]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      {isLoading && <Skeleton rows={8} />}
      {isError && (
        <Notice>
          {error instanceof Error ? error.message : "Could not load diff"}
          {isConsole(target)
            ? " — combined stdout may be missing for this run or the previous one."
            : " — the output file for this result isn't present in storage."}
        </Notice>
      )}
      {data && (
        <>
          <div className="mb-2 flex gap-3 text-[11px] text-faint">
            <span>
              <span className="text-destructive">−</span>{" "}
              {consoleTarget ? "previous run" : "expected"}
            </span>
            <span>
              <span className="text-success">+</span> {consoleTarget ? "this run" : "actual"}
            </span>
            <span>highlighted = the part that changed</span>
          </div>
          {/* Wrapped, not scrolled: caption lines run long, and a sideways
              scroll pushed the text past the tinted line backgrounds. */}
          <div className="rounded-lg border bg-muted/30 py-2 font-mono text-[11px] leading-relaxed">
            {rows.length === 0 ? (
              <span className="px-3 text-faint">Diff is empty.</span>
            ) : (
              rows.map((row) => (
                <div
                  key={row.id}
                  className={cn(
                    "flex gap-2 whitespace-pre-wrap px-3 [overflow-wrap:anywhere]",
                    ROW_TONE[row.kind],
                    row.kind === "add" && "mb-1",
                  )}
                >
                  <span className="w-2 shrink-0 select-none opacity-60">
                    {ROW_SIGN[row.kind]}
                  </span>
                  <span className="min-w-0 flex-1">
                    {row.kind === "del" || row.kind === "add" ? (
                      <Segs segs={row.segs} kind={row.kind} />
                    ) : (
                      row.segs[0].text || " "
                    )}
                  </span>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The sample playing above its two caption tracks.
 *
 * Browsers decode very little of this library — most of it is broadcast
 * captures in containers no browser ships a demuxer for — so the player is
 * offered optimistically and the element's own error event decides whether it
 * worked. When it cannot play, the two tracks are still worth reading side by
 * side, and the sample is one click away for a local player.
 */
function PlaybackPane({ target }: Readonly<{ target: OutputDiffTarget }>) {
  const video = useRef<HTMLVideoElement>(null);
  const [at, setAt] = useState(0);
  // The element's own error code, kept rather than a boolean: a container no
  // browser can demux and a signed URL that never arrived look identical on
  // screen but mean completely different things to whoever has to fix it.
  const [failure, setFailure] = useState<number | null>(null);

  const file = useQuery({
    queryKey: ["sample-file", target.sampleId],
    staleTime: 300_000,
    retry: false,
    queryFn: () => sampleFile(target.sampleId),
  });

  const expected = useOutput(target, "expected");
  const actual = useOutput(target, "actual");

  // The baseline is what the sample is supposed to say, so it doubles as the
  // player's caption track. Held as a blob rather than a request, since the
  // cues are already parsed and in memory.
  const captions = useMemo(() => {
    const vtt = cuesToVtt(expected.data?.cues ?? []);
    return URL.createObjectURL(new Blob([vtt], { type: "text/vtt" }));
  }, [expected.data]);
  useEffect(() => () => URL.revokeObjectURL(captions), [captions]);

  // Cue n of the baseline against cue n of the output, so the columns mark
  // what changed. ponytail: paired by position; an inserted or dropped cue
  // shifts every later pair, align by timing if that turns out common.
  const marks = useMemo(() => {
    const e = expected.data?.cues ?? [];
    const a = actual.data?.cues ?? [];
    const left = e.map((c) => cueMark(c, undefined));
    const right = a.map((c) => cueMark(c, undefined));
    for (let k = 0; k < Math.min(e.length, a.length); k++) {
      const [l, r] = wordDiff(e[k].text, a[k].text);
      left[k] = cueMark(e[k], a[k], l);
      right[k] = cueMark(a[k], e[k], r);
      // Flag both sides: an inserted space only has a changed token on one.
      const differs = left[k].timing !== null || [...l, ...r].some((s) => s.changed);
      left[k].differs = right[k].differs = differs;
    }
    return { left, right };
  }, [expected.data, actual.data]);

  const seek = (t: number) => {
    if (!video.current) return;
    video.current.currentTime = t;
    video.current.play().catch(() => {});
  };

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {file.isLoading && (
        <div className="mb-4 aspect-video animate-pulse rounded-lg bg-muted/60" />
      )}

      {file.data?.download_url && failure === null && (
        <video
          ref={video}
          src={file.data.download_url}
          controls
          onTimeUpdate={(e) => setAt(e.currentTarget.currentTime)}
          onError={(e) => setFailure(e.currentTarget.error?.code ?? 4)}
          className="mb-4 max-h-[46vh] w-full rounded-lg border bg-black"
        >
          <track kind="captions" srcLang="en" label="Expected" src={captions} default />
        </video>
      )}

      {(failure !== null || (file.data && !file.data.download_url) || file.isError) && (
        <Notice>
          {file.data?.download_url ? (
            <>
              {failure === MEDIA_ERR_SRC_NOT_SUPPORTED
                ? "No browser ships a demuxer for this container, which covers most of the broadcast captures in this library."
                : "The sample did not download — its storage link may have expired."}
              <a
                href={file.data.download_url}
                className="ml-1 inline-flex items-center gap-1 font-medium underline"
              >
                <Download className="size-3" /> Download {file.data.filename}
              </a>
            </>
          ) : (
            <>
              This sample has no shared copy to stream — the only one is on the
              platform's own disk.
            </>
          )}{" "}
          The captions below still line up by timecode.
        </Notice>
      )}

      <div className="grid min-h-0 grid-cols-2 gap-3">
        <CueColumn title="Expected" tone="ok" q={expected} marks={marks.left} at={at} onSeek={seek} />
        <CueColumn title="Actual" tone="bad" q={actual} marks={marks.right} at={at} onSeek={seek} />
      </div>
    </div>
  );
}

/** How one cue differs from the cue in the same position on the other side. */
interface CueMark {
  segs: Seg[];
  /** Exact timing of both sides when they disagree, else null. */
  timing: string | null;
  /** Text or timing differs from the twin cue. */
  differs: boolean;
}

/** Second-and-millisecond stamp, since timing drift is usually one frame. */
const exact = (t: number) => `${clock(t)}.${String(Math.round((t % 1) * 1000)).padStart(3, "0")}`;

function cueMark(c: Cue, twin: Cue | undefined, segs?: Seg[]): CueMark {
  const shifted = twin && (twin.start !== c.start || twin.end !== c.end);
  return {
    segs: segs ?? whole(c.text),
    timing: shifted ? `${exact(c.start)} → ${exact(c.end)}` : null,
    differs: false,
  };
}

function useOutput(target: OutputDiffTarget, which: "expected" | "actual") {
  return useQuery({
    queryKey: ["output-text", target.runId, target.regressionId, target.outputId, which],
    staleTime: Infinity,
    retry: false,
    queryFn: async () => {
      const file = await outputText(target, which);
      return { ...file, cues: parseCues(file.content) };
    },
  });
}

type OutputQuery = ReturnType<typeof useOutput>;

function CueColumn({
  title,
  tone,
  q,
  marks,
  at,
  onSeek,
}: Readonly<{
  title: string;
  tone: "ok" | "bad";
  q: OutputQuery;
  marks: CueMark[];
  at: number;
  onSeek: (t: number) => void;
}>) {
  return (
    <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5">
        <span
          className={cn(
            "text-[10px] font-semibold uppercase tracking-wider",
            tone === "ok" ? "text-success" : "text-destructive",
          )}
        >
          {title}
        </span>
        {q.data && (
          <span
            className="ml-auto truncate font-mono text-[10px] text-faint"
            title={q.data.filename}
          >
            {q.data.cues.length > 0 ? `${q.data.cues.length} cues` : q.data.filename}
          </span>
        )}
      </div>
      <div className="max-h-[38vh] min-h-0 flex-1 overflow-auto">
        {q.isLoading && (
          <div className="p-3">
            <Skeleton rows={6} />
          </div>
        )}
        {q.isError && (
          <p className="p-3 text-[11px] text-faint">
            {title === "Actual"
              ? "This run produced no output for the test."
              : "No baseline file is present in storage."}
          </p>
        )}
        {q.data?.cues.length === 0 && (
          // Plain transcripts carry no timings, so there is nothing to sync.
          <pre className="whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed">
            {q.data.content.trim() || <span className="text-faint">Empty file.</span>}
          </pre>
        )}
        {q.data?.cues.map((c, i) => (
          <CueRow
            key={`${c.start}-${c.end}`}
            cue={c}
            mark={marks[i]}
            kind={tone === "ok" ? "del" : "add"}
            active={at >= c.start && at < c.end}
            onSeek={onSeek}
          />
        ))}
        {q.data?.truncated && (
          <p className="border-t px-3 py-1.5 text-[10px] text-faint">Truncated at 1 MiB.</p>
        )}
      </div>
    </div>
  );
}

function CueRow({
  cue,
  mark,
  kind,
  active,
  onSeek,
}: Readonly<{
  cue: Cue;
  mark: CueMark | undefined;
  kind: "del" | "add";
  active: boolean;
  onSeek: (t: number) => void;
}>) {
  const differs = !!mark?.differs;
  return (
    <button
      // Keeping the playing cue in view is what makes two columns readable
      // while the video runs; "nearest" stops it dragging the drawer around.
      ref={active ? (el) => el?.scrollIntoView({ block: "nearest" }) : undefined}
      onClick={() => onSeek(cue.start)}
      className={cn(
        "flex w-full cursor-pointer gap-2 border-b px-3 py-1 text-left transition-colors last:border-0 hover:bg-muted/60",
        active && "bg-primary/10",
        differs && "border-l-2 border-l-warning",
      )}
    >
      <span
        className={cn(
          "shrink-0 pt-px font-mono text-[10px] tabular-nums text-faint",
          mark?.timing && cn("rounded-sm px-0.5", MARK_TONE[kind]),
        )}
      >
        {mark?.timing ?? clock(cue.start)}
      </span>
      <span className="min-w-0 flex-1 whitespace-pre-wrap font-mono text-[11px] leading-relaxed [overflow-wrap:anywhere]">
        {mark ? <Segs segs={mark.segs} kind={kind} /> : cue.text}
      </span>
    </button>
  );
}

function Skeleton({ rows }: Readonly<{ rows: number }>) {
  return (
    <div className="flex flex-col gap-1.5">
      {Array.from({ length: rows }, (_, n) => `placeholder-${n}`).map((id) => (
        <div key={id} className="h-4 animate-pulse rounded bg-muted/70" />
      ))}
    </div>
  );
}

function Notice({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-4 rounded-lg border border-warning/40 bg-warning/8 p-3 text-xs text-warning">
      {children}
    </div>
  );
}
