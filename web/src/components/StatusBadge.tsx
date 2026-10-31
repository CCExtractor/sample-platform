import type { RunStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Colored dot + quiet label; in-flight states pulse. */
const RUN_STATUS: Record<RunStatus, { label: string; dot: string; pulse?: boolean }> = {
  queued: { label: "Queued", dot: "bg-faint" },
  running: { label: "Running", dot: "bg-primary", pulse: true },
  pass: { label: "Passed", dot: "bg-success" },
  fail: { label: "Failed", dot: "bg-destructive" },
  canceled: { label: "Canceled", dot: "bg-faint" },
  error: { label: "Error", dot: "bg-destructive" },
  incomplete: { label: "Incomplete", dot: "bg-warning" },
  preparation: { label: "Preparing", dot: "bg-warning", pulse: true },
  building: { label: "Building", dot: "bg-warning", pulse: true },
  testing: { label: "Testing", dot: "bg-primary", pulse: true },
  completed: { label: "Completed", dot: "bg-success" },
};

export function RunStatusBadge({ status, className }: Readonly<{ status: RunStatus; className?: string }>) {
  const s = RUN_STATUS[status] ?? RUN_STATUS.queued;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground", className)}>
      <span className="relative flex size-2">
        {s.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", s.dot)} />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", s.dot)} />
      </span>
      {s.label}
    </span>
  );
}
