import * as DialogPrimitive from "@radix-ui/react-dialog";
import { TriangleAlert } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import * as React from "react";

import { Button } from "@/components/ui/button";

/** Deliberate-action dialog for destructive operations. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  body,
  confirmLabel,
  busy,
  onConfirm,
}: Readonly<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
}>) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[2px]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content asChild forceMount>
              <motion.div
                className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card p-5 shadow-pop outline-none"
                initial={{ opacity: 0, scale: 0.96, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96, y: 8 }}
                transition={{ type: "spring", stiffness: 500, damping: 38 }}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                    <TriangleAlert className="size-4" />
                  </span>
                  <DialogPrimitive.Title className="text-[14px] font-semibold tracking-tight">
                    {title}
                  </DialogPrimitive.Title>
                </div>
                <div className="mb-4 text-[13px] leading-relaxed text-muted-foreground">
                  {body}
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                    Cancel
                  </Button>
                  <Button variant="destructive" size="sm" disabled={busy} onClick={onConfirm}>
                    {confirmLabel}
                  </Button>
                </div>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}
