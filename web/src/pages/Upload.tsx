import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileVideo, Loader2, UploadCloud, XCircle } from "lucide-react";
import { motion } from "motion/react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  discardUpload,
  finalizeUpload,
  linkUpload,
  uploadSample,
  useAbout,
  useFtpCredentials,
  useQueuedSamples,
  useSamples,
  type FtpCredentials,
  type QueuedSample,
} from "@/lib/api";
import type { Platform } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Picked {
  file: File;
  sha: string | null; // null while hashing
  duplicateOf: string | null;
  tooLarge?: boolean;
}

// crypto.subtle has no streaming API, so hashing means loading the whole
// file into memory. Past this size that risks killing the tab — skip the
// browser-side duplicate check and let the server catch it instead.
const HASH_LIMIT = 1024 ** 3; // 1 GiB

/**
 * Sample upload, in the two steps the platform actually works in: the bytes
 * go into a queue first, and the description that turns a queued file into
 * a sample follows separately.
 *
 * Files are hashed in the browser and checked against the library before
 * any transfer, so a duplicate is caught up front rather than after a
 * multi-gigabyte upload. The server checks again on arrival, since another
 * upload can land in between.
 */
export function Upload() {
  const { data: samples = [] } = useSamples();
  const qc = useQueryClient();
  const [items, setItems] = useState<Picked[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Too big to hash in the browser still uploads: the server hashes it and
  // rejects a duplicate there, which is the check that actually counts.
  const ready = items.filter(
    (it) => !it.duplicateOf && (it.sha !== null || it.tooLarge),
  );

  const sendAll = async () => {
    setUploading(true);
    setUploadError(null);
    try {
      for (const item of ready) {
        await uploadSample(item.file);
        setItems((prev) => prev.filter((it) => it.file !== item.file));
      }
      await qc.invalidateQueries({ queryKey: ["queued-samples"] });
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const addFiles = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      if (file.size > HASH_LIMIT) {
        setItems((prev) => [...prev, { file, sha: null, duplicateOf: null, tooLarge: true }]);
        continue;
      }
      const entry: Picked = { file, sha: null, duplicateOf: null };
      setItems((prev) => [...prev, entry]);
      const buf = await file.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", buf);
      const sha = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
      const dup = samples.find((s) => s.sha === sha);
      setItems((prev) =>
        prev.map((it) =>
          it.file === file ? { ...it, sha, duplicateOf: dup?.original_name ?? null } : it,
        ),
      );
    }
  };

  return (
    <div>
      <div className="sticky top-0 z-10 border-b bg-card/85 px-6 py-3 backdrop-blur">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-semibold tracking-tight">Sample upload</h1>
          <span className="text-xs text-faint">
            files are checked against the library before uploading
          </span>
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-6 py-6">
        {/* A button rather than a div: dropping is a convenience, but opening
            the picker has to work from the keyboard too, and a button gets
            that plus a focus ring for free. */}
        <button
          type="button"
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex w-full cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            dragging ? "border-primary bg-accent/40" : "hover:border-border-strong hover:bg-muted/40",
          )}
        >
          <UploadCloud className={cn("size-8", dragging ? "text-primary" : "text-faint")} />
          <div className="text-[13px] font-medium">
            Drop media samples here, or click to browse
          </div>
          <div className="text-[11px] text-faint">
            Each file is SHA-256 hashed locally and checked against the {samples.length}-sample
            library before upload.
          </div>
        </button>
        {/* Outside the button: a form control nested in one is invalid, and
            browsers disagree about whether the click even reaches it. */}
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />

        <div className="mt-4 flex flex-col gap-2">
          {items.map((it) => (
            <motion.div
              key={`${it.file.name}-${it.file.size}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-3 rounded-xl border bg-card p-3 shadow-card"
            >
              <FileVideo className="size-4 shrink-0 text-faint" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium">{it.file.name}</div>
                <div className="font-mono text-[10px] text-faint">
                  {(it.file.size / 1_048_576).toFixed(1)} MB
                  {it.sha && ` · ${it.sha.slice(0, 20)}…`}
                </div>
              </div>
              <PickedStatus item={it} />
            </motion.div>
          ))}
        </div>

        {ready.length > 0 && (
          <div className="mt-4 flex items-center justify-between rounded-xl border bg-card p-4 shadow-card">
            <div className="text-[12px] text-faint">
              {ready.length} file{ready.length > 1 ? "s" : ""} ready.
              {uploadError && (
                <span className="ml-2 text-destructive">{uploadError}</span>
              )}
            </div>
            <Button size="sm" disabled={uploading} onClick={sendAll}>
              {uploading ? <Loader2 className="animate-spin" /> : <UploadCloud />}
              {uploading ? "Uploading" : "Upload to queue"}
            </Button>
          </div>
        )}

        <UploadQueue />

        <FtpPanel />
      </div>
    </div>
  );
}

/**
 * The queue between an upload and a sample.
 *
 * Each row can go three ways: describe it into a new sample, attach it to
 * one that already exists, or throw it away. Describing needs a CCExtractor
 * version, which is why the platform splits this from the transfer at all.
 */
function UploadQueue() {
  const { data: queued = [], isLoading } = useQueuedSamples();
  const [active, setActive] = useState<number | null>(null);

  if (isLoading || queued.length === 0) return null;

  return (
    <section className="mt-8">
      <SectionLabel>In the queue · {queued.length}</SectionLabel>
      <div className="flex flex-col gap-2">
        {queued.map((q) => (
          <QueueRow
            key={q.id}
            item={q}
            open={active === q.id}
            onToggle={() => setActive(active === q.id ? null : q.id)}
          />
        ))}
      </div>
    </section>
  );
}

function QueueRow({
  item,
  open,
  onToggle,
}: Readonly<{
  item: QueuedSample;
  open: boolean;
  onToggle: () => void;
}>) {
  const qc = useQueryClient();
  const { data: about } = useAbout();
  const { data: samples = [] } = useSamples();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState("");
  const [platform, setPlatform] = useState<Platform>("linux");
  const [notes, setNotes] = useState("");
  const [linkTo, setLinkTo] = useState("");

  // The platform reports the release under test, which is the version an
  // uploader almost always means.
  const versionValue = version || about?.ccextractor_version || "";

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["queued-samples"] });
      await qc.invalidateQueries({ queryKey: ["samples"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-card">
      <button
        onClick={onToggle}
        className="flex w-full cursor-pointer items-center gap-3 px-4 py-2.5 text-left"
      >
        <FileVideo className="size-4 shrink-0 text-faint" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium">
            {item.original_name}
            {item.extension}
          </div>
          <code className="text-[10px] text-faint">{item.sha.slice(0, 24)}…</code>
        </div>
        <Badge variant="secondary">queued</Badge>
      </button>

      {open && (
        <div className="border-t bg-muted/30 px-4 py-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <label htmlFor="upload-version" className="text-[11px] text-faint">
              CCExtractor version
              <Input
                id="upload-version"
                className="mt-1 h-7 text-xs"
                value={versionValue}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="0.94"
              />
            </label>
            <label className="text-[11px] text-faint">
              <span>Platform</span>
              <select
                className="mt-1 h-7 w-full rounded-lg border bg-card px-2 text-[12px]"
                value={platform}
                onChange={(e) => setPlatform(e.target.value as Platform)}
              >
                <option value="linux">linux</option>
                <option value="windows">windows</option>
              </select>
            </label>
            <label htmlFor="upload-notes" className="text-[11px] text-faint">
              Notes
              <Input
                id="upload-notes"
                className="mt-1 h-7 text-xs"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="anything odd about it"
              />
            </label>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={busy || !versionValue}
              onClick={() =>
                act(() =>
                  finalizeUpload(item.id, {
                    version: versionValue,
                    platform,
                    notes,
                  }),
                )
              }
            >
              {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
              Make it a sample
            </Button>

            <span className="text-[11px] text-faint">or attach to</span>
            <select
              className="h-7 max-w-56 rounded-lg border bg-card px-2 text-[12px]"
              value={linkTo}
              onChange={(e) => setLinkTo(e.target.value)}
            >
              <option value="">an existing sample…</option>
              {samples.slice(0, 200).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.original_name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy || !linkTo}
              onClick={() => act(() => linkUpload(item.id, Number(linkTo)))}
            >
              Attach
            </Button>

            <Button
              size="sm"
              variant="ghost"
              className="ml-auto text-destructive"
              disabled={busy}
              onClick={() => act(() => discardUpload(item.id))}
            >
              <XCircle /> Discard
            </Button>
          </div>

          {error && (
            <div className="mt-2 text-[11px] text-destructive">{error}</div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * FTP details for the ingest server.
 *
 * Behind a click because it shows a working password, and because asking
 * for it is what creates the account the first time.
 */
function FtpPanel() {
  const [shown, setShown] = useState(false);
  const { data, isLoading } = useFtpCredentials(shown);

  return (
    <section className="mt-8">
      <SectionLabel>Upload over FTP</SectionLabel>
      <div className="rounded-xl border bg-card p-4 shadow-card">
        <p className="text-[12px] text-faint">
          For files too large to push through the browser. The platform picks
          up anything dropped into your FTP folder.
        </p>
        <FtpDetails shown={shown} reveal={() => setShown(true)} isLoading={isLoading} data={data} />
      </div>
    </section>
  );
}

/** Where a picked file stands: too big to hash, hashing, duplicate, or new. */
function PickedStatus({ item }: Readonly<{ item: Picked }>) {
  if (item.tooLarge) {
    return (
      <Badge
        variant="secondary"
        title="Too big to hash in the browser — the server checks for duplicates on upload"
      >
        dup check on server
      </Badge>
    );
  }
  if (item.sha === null) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-faint">
        <Loader2 className="size-3 animate-spin" /> hashing
      </span>
    );
  }
  if (item.duplicateOf) {
    return (
      <Badge variant="warning">
        <XCircle className="size-3" /> already in library: {item.duplicateOf}
      </Badge>
    );
  }
  return (
    <Badge variant="success">
      <CheckCircle2 className="size-3" /> new sample
    </Badge>
  );
}

/**
 * FTP credentials, hidden until asked for.
 *
 * They are only fetched on reveal, so an unopened page never pulls a password
 * it is not going to show.
 */
function FtpDetails({
  shown,
  reveal,
  isLoading,
  data,
}: Readonly<{
  shown: boolean;
  reveal: () => void;
  isLoading: boolean;
  data: FtpCredentials | undefined;
}>) {
  if (!shown) {
    return (
      <Button size="sm" variant="secondary" className="mt-3" onClick={reveal}>
        Show my FTP details
      </Button>
    );
  }
  if (isLoading) {
    return (
      <div className="mt-3 flex items-center gap-2 text-[12px] text-faint">
        <Loader2 className="size-3 animate-spin" /> fetching
      </div>
    );
  }
  if (!data) return null;
  return (
    <dl className="mt-3 grid grid-cols-[110px_1fr] gap-y-1 text-[12px]">
      <dt className="text-faint">Host</dt>
      <dd><code>{data.host}</code></dd>
      <dt className="text-faint">Port</dt>
      <dd><code>{data.port}</code></dd>
      <dt className="text-faint">Username</dt>
      <dd><code>{data.username}</code></dd>
      <dt className="text-faint">Password</dt>
      <dd><code className="break-all">{data.password}</code></dd>
    </dl>
  );
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </div>
  );
}
