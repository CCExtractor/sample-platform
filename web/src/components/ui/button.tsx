import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "press inline-flex cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-lg text-[13px] font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover",
        secondary:
          "border border-border bg-card text-foreground shadow-xs hover:bg-muted",
        outline:
          "border border-border bg-transparent hover:bg-muted hover:border-border-strong",
        ghost: "text-muted-foreground hover:bg-muted hover:text-foreground",
        destructive: "bg-destructive text-white shadow-sm hover:opacity-90",
      },
      size: {
        default: "h-8 px-3.5",
        sm: "h-7 rounded-md px-2.5 text-xs",
        lg: "h-9 rounded-lg px-5",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  ...props
}: Readonly<React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>>) {
  return (
    <button className={cn(buttonVariants({ variant, size, className }))} {...props} />
  );
}

export { Button, buttonVariants };
