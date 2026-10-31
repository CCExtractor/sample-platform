import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Persisted, draggable width for a pane. Returns the current width and a
 * <ResizeHandle> to drop on the pane's trailing edge.
 *
 * Pass edge="leading" for a pane anchored to the right of the screen: its
 * handle sits on the left, where dragging towards the left has to widen
 * rather than narrow it.
 */
export function useResizableWidth(
  key: string,
  initial: number,
  min: number,
  max: number,
  edge: "trailing" | "leading" = "trailing",
) {
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(`sp-w-${key}`));
    return saved >= min && saved <= max ? saved : initial;
  });
  const dragging = useRef(false);
  const sign = edge === "leading" ? -1 : 1;

  const onMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      setWidth((w) => {
        const next = Math.min(max, Math.max(min, w + sign * e.movementX));
        return next;
      });
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setWidth((w) => {
        localStorage.setItem(`sp-w-${key}`, String(w));
        return w;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [key, min, max, sign]);

  // A splitter has to be operable without a mouse, so the same width change
  // is reachable from the arrow keys. Shift moves in coarser steps.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const step = (e.shiftKey ? 40 : 8) * (e.key === "ArrowRight" ? 1 : -1) * sign;
    setWidth((w) => {
      const next = Math.min(max, Math.max(min, w + step));
      localStorage.setItem(`sp-w-${key}`, String(next));
      return next;
    });
  };

  // role="slider" rather than "separator": what this actually is, to both a
  // screen reader and a linter, is a one-dimensional value the user drags or
  // arrows between a min and a max. A focusable separator is the older
  // window-splitter idiom and reads as non-interactive.
  const handle = (
    <div
      onMouseDown={onMouseDown}
      onKeyDown={onKeyDown}
      tabIndex={0}
      className={cn(
        "group relative z-10 w-2 shrink-0 cursor-col-resize",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        edge === "leading" ? "-ml-1" : "-mr-1",
      )}
      role="slider"
      aria-orientation="vertical"
      aria-label="Resize pane"
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
    >
      <div
        className={cn(
          "absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors",
          "group-hover:bg-primary/60 group-active:bg-primary",
        )}
      />
    </div>
  );

  return { width, handle };
}
