import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, ...props }: Readonly<React.ComponentProps<"input">>) {
  return (
    <input
      className={cn(
        "flex h-8 w-full rounded-lg border bg-card px-3 py-1 text-[13px] shadow-card transition-all duration-150 placeholder:text-faint hover:border-border-strong focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

function Textarea({ className, ...props }: Readonly<React.ComponentProps<"textarea">>) {
  return (
    <textarea
      className={cn(
        "flex min-h-16 w-full rounded-lg border bg-card px-3 py-2 text-[13px] shadow-card transition-all duration-150 placeholder:text-faint hover:border-border-strong focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Input, Textarea };
