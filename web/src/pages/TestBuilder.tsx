import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  FileVideo,
  FlaskConical,
  Loader2,
  Play,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { useQueryClient } from "@tanstack/react-query";

import {
  commandPresets,
  createRegressionTest,
  deriveCategories,
  useRegressionTests,
  useSamples,
} from "@/lib/api";
import { COMMAND_MAX } from "@/lib/validate";
import type { Sample } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Sample", "Command", "Describe"] as const;

/**
 * Guided test creation. The test is stored as inactive ("draft") — the
 * follow-up is a real verification run on CI (offered on the success
 * screen), and activation happens from the test detail once a baseline
 * exists. No step here pretends to run anything.
 */
export function TestBuilder() {
  const [step, setStep] = useState(0);
  const [sample, setSample] = useState<Sample | null>(null);
  const [command, setCommand] = useState("");
  const [expectedRc, setExpectedRc] = useState(0);
  const [description, setDescription] = useState("");
  const [selectedCats, setSelectedCats] = useState<string[]>([]);
  const [saved, setSaved] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const create = async () => {
    if (!sample) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await createRegressionTest({
        sample_id: sample.id,
        command,
        expected_rc: expectedRc,
        description,
        categories: selectedCats,
      });
      await qc.invalidateQueries({ queryKey: ["regression-tests"] });
      setSaved(res.regression_test_id);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  const canNext =
    (step === 0 && !!sample) ||
    (step === 1 && command.trim().length > 0) ||
    step === 2;

  if (saved !== null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
        <motion.div
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
        >
          <CheckCircle2 className="size-14 text-success" />
        </motion.div>
        <h1 className="text-[17px] font-semibold tracking-tight">
          Test #{saved} created as a draft
        </h1>
        <p className="max-w-md text-[13px] text-faint">
          It stays inactive until its output is verified and a baseline is
          recorded. Queue a run scoped to this test to see what it produces on
          both platforms.
        </p>
        <div className="flex gap-2">
          <Button onClick={() => navigate({ to: "/runs/new", search: { test: saved } })}>
            <Play /> Queue verification run
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate({ to: "/tests", search: { t: saved } })}
          >
            Open test #{saved}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setStep(0); setSample(null); setCommand(""); setExpectedRc(0);
              setDescription(""); setSelectedCats([]); setSaved(null);
            }}
          >
            Create another
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-7 flex items-center gap-3">
        <Link to="/tests">
          <Button variant="ghost" size="icon"><ChevronLeft /></Button>
        </Link>
        <div>
          <h1 className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
            <FlaskConical className="size-4 text-primary" /> New regression test
          </h1>
          <p className="text-[13px] text-faint">
            Define the test, verify its output on a run, then activate it.
          </p>
        </div>
      </div>

      {/* Stepper */}
      <ol className="mb-8 flex items-center gap-1">
        {STEPS.map((label, i) => (
          <li key={label} className="flex flex-1 items-center gap-1">
            <button
              onClick={() => i < step && setStep(i)}
              className={cn(
                "flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                i === step && "bg-primary text-primary-foreground shadow-sm",
                i < step && "cursor-pointer bg-success/10 text-success",
                i > step && "bg-muted text-faint",
              )}
            >
              <span className="flex size-4 items-center justify-center rounded-full border border-current text-[10px]">
                {i < step ? <Check className="size-3" /> : i + 1}
              </span>
              {label}
            </button>
            {i < STEPS.length - 1 && <div className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <motion.div
        key={step}
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
      >
        {step === 0 && <StepSample selected={sample} onSelect={setSample} />}
        {step === 1 && sample && (
          <StepCommand
            sample={sample}
            command={command}
            setCommand={setCommand}
            expectedRc={expectedRc}
            setExpectedRc={setExpectedRc}
          />
        )}
        {step === 2 && (
          <StepDescribe
            description={description}
            setDescription={setDescription}
            selectedCats={selectedCats}
            setSelectedCats={setSelectedCats}
          />
        )}
      </motion.div>

      <div className="mt-8 flex justify-between">
        <Button variant="outline" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          <ArrowLeft /> Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
            Continue <ArrowRight />
          </Button>
        ) : (
          <div className="flex items-center gap-2">
            {saveError && <span className="text-[11px] text-destructive">{saveError}</span>}
            <Button disabled={selectedCats.length === 0 || saving} onClick={create}>
              {saving ? <Loader2 className="animate-spin" /> : <Sparkles />} Create draft test
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

/* Step 1 — sample picker with context card */
function StepSample({ selected, onSelect }: Readonly<{ selected: Sample | null; onSelect: (s: Sample) => void }>) {
  const [q, setQ] = useState("");
  const { data: allSamples = [] } = useSamples();
  const { data: tests = [] } = useRegressionTests();
  const filtered = allSamples
    .filter((s) =>
      `${s.original_name} ${s.tags.join(" ")} ${s.extension}`.toLowerCase().includes(q.toLowerCase()),
    )
    .slice(0, 40);
  const existing = selected ? tests.filter((t) => t.sample_id === selected.id) : [];

  return (
    <div className="grid grid-cols-5 gap-4">
      <div className="col-span-3">
        <Input
          placeholder={`Search ${allSamples.length} samples by name, tag, extension…`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="mb-2"
        />
        <div className="flex max-h-96 flex-col gap-0.5 overflow-y-auto rounded-xl border bg-card p-1 shadow-card">
          {filtered.map((s) => (
            <button
              key={s.id}
              onClick={() => onSelect(s)}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] transition-colors",
                selected?.id === s.id ? "bg-accent text-accent-foreground" : "hover:bg-muted/70",
              )}
            >
              <FileVideo className="size-4 shrink-0 text-faint" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{s.original_name}</div>
                <div className="text-[11px] text-faint">
                  {s.extension} · {s.test_count} existing test{s.test_count === 1 ? "" : "s"}
                </div>
              </div>
              {s.tags.slice(0, 2).map((t) => (
                <Badge key={t} variant="secondary">{t}</Badge>
              ))}
            </button>
          ))}
        </div>
      </div>
      <div className="col-span-2">
        {selected ? (
          <div className="rounded-xl border bg-card p-4 text-sm shadow-card">
            <div className="mb-2 truncate text-[13px] font-semibold">{selected.original_name}</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
              <dt className="text-faint">Extension</dt>
              <dd className="font-mono">{selected.extension}</dd>
              <dt className="text-faint">SHA</dt>
              <dd className="truncate font-mono">{selected.sha.slice(0, 18)}…</dd>
              <dt className="text-faint">Tags</dt>
              <dd>{selected.tags.length ? selected.tags.join(", ") : "—"}</dd>
            </dl>
            {existing.length > 0 && (
              <div className="mt-3 border-t pt-2">
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">
                  Existing tests on this sample
                </div>
                {existing.slice(0, 4).map((t) => (
                  <div key={t.id} className="truncate font-mono text-[11px] text-muted-foreground">
                    #{t.id} {t.command}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center rounded-xl border border-dashed p-4 text-center text-[13px] text-faint">
            Select a sample to see its context and existing tests
          </div>
        )}
      </div>
    </div>
  );
}

/* Step 2 — command composer, presets mined from the real suite */
function StepCommand({
  sample, command, setCommand, expectedRc, setExpectedRc,
}: Readonly<{
  sample: Sample;
  command: string;
  setCommand: (c: string) => void;
  expectedRc: number;
  setExpectedRc: (n: number) => void;
}>) {
  const { data: tests = [] } = useRegressionTests();
  const presets = commandPresets(tests, 6);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          Common commands in the suite
        </div>
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => (
            <button
              key={p.command}
              onClick={() => setCommand(p.command)}
              className={cn(
                "cursor-pointer rounded-lg border px-2.5 py-1.5 font-mono text-[11px] transition-all duration-150",
                command === p.command
                  ? "border-primary/40 bg-accent text-accent-foreground"
                  : "hover:border-border-strong hover:bg-muted/60",
              )}
            >
              {p.command} <span className="ml-1 text-faint">×{p.count}</span>
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          Command
        </div>
        <div className="overflow-hidden rounded-xl border bg-card shadow-card">
          <div className="border-b bg-muted/40 px-3 py-1.5 font-mono text-[11px] text-faint">
            ccextractor <span className="text-primary">{sample.original_name}{sample.extension}</span> …
          </div>
          <Textarea
            className="rounded-none border-0 font-mono text-xs shadow-none focus-visible:ring-0"
            placeholder="--autoprogram --out=srt --latin1"
            value={command}
            maxLength={COMMAND_MAX}
            onChange={(e) => setCommand(e.target.value)}
          />
        </div>
        <div className="mt-1 text-[11px] text-warning">
          Runs verbatim on the CI VMs once the test is active — double-check flags.
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">
          Expected return code
        </div>
        <Input
          type="number"
          className="w-24"
          value={expectedRc}
          onChange={(e) => setExpectedRc(Number(e.target.value))}
        />
      </div>
    </div>
  );
}

/* Step 3 — categorize & describe */
function StepDescribe({
  description, setDescription, selectedCats, setSelectedCats,
}: Readonly<{
  description: string;
  setDescription: (d: string) => void;
  selectedCats: string[];
  setSelectedCats: (c: string[]) => void;
}>) {
  const { data: allTests = [] } = useRegressionTests();
  const categories = deriveCategories(allTests);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          Categories <span className="text-destructive">*</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {categories.map((c) => {
            const on = selectedCats.includes(c.name);
            return (
              <button
                key={c.id}
                onClick={() =>
                  setSelectedCats(
                    on ? selectedCats.filter((x) => x !== c.name) : [...selectedCats, c.name],
                  )
                }
                className={cn(
                  "cursor-pointer rounded-full border px-3 py-1 text-xs transition-all duration-150",
                  on
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {c.name}
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          Description
        </div>
        <Textarea
          placeholder="What does this test verify, and why does it exist?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
    </div>
  );
}
