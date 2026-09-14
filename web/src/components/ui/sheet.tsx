import * as DialogPrimitive from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import * as React from "react";

import { useResizableWidth } from "@/components/ResizeHandle";
import { cn } from "@/lib/utils";

const Sheet = DialogPrimitive.Root;
const SheetTrigger = DialogPrimitive.Trigger;
const SheetClose = DialogPrimitive.Close;

/**
 * Right-hand drawer with spring slide-in. Pass `open` to drive the
 * enter/exit animation via AnimatePresence.
 *
 * Naming a `resizeKey` makes the drawer drag-resizable, remembering its
 * width under that key. Without one it keeps the fixed max-width, so
 * callers that never needed resizing are unaffected.
 */
function AnimatedSheet({
  open,
  onOpenChange,
  children,
  className,
  resizeKey,
}: Readonly<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
  resizeKey?: string;
}>) {
  // Handle sits on the left: the panel is anchored to the right edge, so
  // that is the only side whose position changes with the width.
  const { width, handle } = useResizableWidth(
    resizeKey ?? "sheet",
    576,
    380,
    1180,
    "leading",
  );

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[2px]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content asChild forceMount>
              <motion.div
                className={cn(
                  "fixed inset-y-2 right-2 z-50 flex overflow-hidden rounded-xl border bg-card shadow-pop outline-none",
                  !resizeKey && "w-full max-w-xl",
                  className,
                )}
                style={resizeKey ? { width } : undefined}
                initial={{ x: 48, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 48, opacity: 0 }}
                transition={{ type: "spring", stiffness: 420, damping: 36 }}
              >
                {resizeKey && handle}
                <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                  {children}
                </div>
                <DialogPrimitive.Close className="absolute right-3.5 top-3.5 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
                  <X className="size-4" />
                </DialogPrimitive.Close>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}

const SheetTitle = DialogPrimitive.Title;
const SheetDescription = DialogPrimitive.Description;

export { Sheet, SheetTrigger, SheetClose, AnimatedSheet, SheetTitle, SheetDescription };
