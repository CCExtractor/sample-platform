import { useNavigate } from "@tanstack/react-router";
import { Activity, FileVideo, FlaskConical, Gauge, Home, Search } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useRegressionTests, useSamples } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Item {
  id: string;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  go: () => void;
}

/** Real ⌘K palette: pages, regression tests, samples — keyboard-first. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const { data: tests = [] } = useRegressionTests();
  const { data: samples = [] } = useSamples();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        setQ("");
        setCursor(0);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const needle = q.trim().toLowerCase();
    const pages: Item[] = [
      { id: "p-home", icon: <Home className="size-3.5" />, title: "Home — triage inbox", go: () => navigate({ to: "/" }) },
      { id: "p-runs", icon: <Activity className="size-3.5" />, title: "Test results", go: () => navigate({ to: "/runs" }) },
      { id: "p-tests", icon: <FlaskConical className="size-3.5" />, title: "Regression tests", go: () => navigate({ to: "/tests" }) },
      { id: "p-samples", icon: <FileVideo className="size-3.5" />, title: "Samples", go: () => navigate({ to: "/samples" }) },
      { id: "p-status", icon: <Gauge className="size-3.5" />, title: "Platform status", go: () => navigate({ to: "/status" }) },
    ];
    if (!needle) return pages;

    const testHits: Item[] = tests
      .filter((t) => `#${t.id} ${t.command} ${t.sample_name}`.toLowerCase().includes(needle))
      .slice(0, 6)
      .map((t) => ({
        id: `t-${t.id}`,
        icon: <FlaskConical className="size-3.5" />,
        title: `#${t.id} ${t.command}`,
        subtitle: t.sample_name,
        go: () => navigate({ to: "/tests", search: { t: t.id } }),
      }));
    const sampleHits: Item[] = samples
      .filter((s) => `${s.original_name} ${s.sha}`.toLowerCase().includes(needle))
      .slice(0, 4)
      .map((s) => ({
        id: `s-${s.id}`,
        icon: <FileVideo className="size-3.5" />,
        title: s.original_name,
        subtitle: s.extension,
        go: () => navigate({ to: "/samples" }),
      }));
    return [
      ...pages.filter((p) => p.title.toLowerCase().includes(needle)),
      ...testHits,
      ...sampleHits,
    ];
  }, [q, tests, samples, navigate]);

  const pick = (item: Item) => {
    item.go();
    setOpen(false);
  };

  return (
    <>
      <button
        className="press flex h-8 w-full cursor-pointer items-center gap-2 rounded-lg border bg-card px-2.5 text-[13px] text-faint shadow-card transition-colors hover:border-border-strong hover:text-muted-foreground"
        onClick={() => setOpen(true)}
      >
        <Search className="size-3.5" />
        Search…
        <kbd className="ml-auto rounded border bg-muted px-1 font-sans text-[10px] text-faint">
          ⌘K
        </kbd>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[16vh] backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            onClick={() => setOpen(false)}
          >
            <motion.div
              className="w-full max-w-lg overflow-hidden rounded-xl border bg-card shadow-pop"
              initial={{ scale: 0.97, y: -8, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.97, y: -8, opacity: 0 }}
              transition={{ type: "spring", stiffness: 500, damping: 38 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-2 border-b px-3.5">
                <Search className="size-4 text-faint" />
                <input
                  ref={inputRef}
                  className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-faint"
                  placeholder="Search tests by id/command, samples, pages…"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setCursor(0);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setCursor((c) => Math.min(c + 1, items.length - 1));
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setCursor((c) => Math.max(c - 1, 0));
                    } else if (e.key === "Enter" && items[cursor]) {
                      pick(items[cursor]);
                    }
                  }}
                />
              </div>
              <div className="max-h-80 overflow-y-auto p-1.5">
                {items.map((item, i) => (
                  <button
                    key={item.id}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => pick(item)}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors",
                      i === cursor ? "bg-accent text-accent-foreground" : "text-muted-foreground",
                    )}
                  >
                    <span className="text-faint">{item.icon}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">{item.title}</span>
                    {item.subtitle && (
                      <span className="shrink-0 text-[11px] text-faint">{item.subtitle}</span>
                    )}
                  </button>
                ))}
                {items.length === 0 && (
                  <div className="px-3 py-8 text-center text-[13px] text-faint">No matches.</div>
                )}
              </div>
              <div className="flex gap-3 border-t bg-muted/40 px-3.5 py-2 text-[10px] text-faint">
                <span>↑↓ navigate</span>
                <span>↵ open</span>
                <span>esc close</span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
