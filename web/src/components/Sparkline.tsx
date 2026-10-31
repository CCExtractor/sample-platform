import type { SparkResult } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Pass/fail history dots, newest last. */
export function Sparkline({ results, className }: Readonly<{ results: SparkResult[]; className?: string }>) {
  if (results.length === 0) {
    return <span className={cn("text-xs text-muted-foreground italic", className)}>no runs yet</span>;
  }
  return (
    <div className={cn("flex items-end gap-[3px]", className)} title={`last ${results.length} runs`}>
      {results.map((r, i) => ({ id: `run-${i}`, r })).map(({ id, r }) => (
        <span
          key={id}
          className={cn(
            "w-[5px] rounded-[1px]",
            r === "pass" && "h-3 bg-success/70",
            r === "fail" && "h-4 bg-destructive",
            r === "skip" && "h-2 bg-muted-foreground/40",
          )}
        />
      ))}
    </div>
  );
}
