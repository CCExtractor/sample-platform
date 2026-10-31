import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-1.5 py-px text-[11px] font-medium leading-4 whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "border border-border bg-muted/60 text-muted-foreground",
        outline: "border border-border text-muted-foreground",
        success: "bg-success/10 text-success",
        destructive: "bg-destructive/10 text-destructive",
        warning: "bg-warning/12 text-warning",
        accent: "bg-accent text-accent-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Badge({
  className,
  variant,
  ...props
}: Readonly<React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
