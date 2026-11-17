import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

/** Pan and zoom of a drawing inside a viewport: `x`, `y` in screen pixels, `k` the scale. */
export interface View {
  x: number;
  y: number;
  k: number;
}

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 2.5;

const clamp = (k: number): number => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, k));

interface Options {
  /** Wheel zooms and the background can be dragged (off for the sidebar preview). */
  interactive: boolean;
}

/**
 * The view of a pannable, zoomable canvas. The wheel zooms around the pointer, dragging
 * the background pans, and `zoomBy`, `fit` and `centerOn` drive it from buttons and keys.
 */
export function usePanZoom({ interactive }: Options) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean } | null>(null);

  const size = (): { w: number; h: number } => {
    const el = viewportRef.current;
    return { w: el?.clientWidth ?? 0, h: el?.clientHeight ?? 0 };
  };

  /** Zoom by `factor` around a point of the viewport (its centre by default). */
  const zoomBy = useCallback((factor: number, at?: { x: number; y: number }) => {
    setView((v) => {
      const { w, h } = size();
      const px = at?.x ?? w / 2;
      const py = at?.y ?? h / 2;
      const k = clamp(v.k * factor);
      const r = k / v.k;
      return { k, x: px - (px - v.x) * r, y: py - (py - v.y) * r };
    });
  }, []);

  /** Show the whole drawing, no larger than `maxK`. */
  const fit = useCallback((width: number, height: number, maxK = 1) => {
    const { w, h } = size();
    if (w === 0 || h === 0 || width === 0 || height === 0) return;
    const k = clamp(Math.min(w / width, h / height, maxK));
    setView({ k, x: (w - width * k) / 2, y: (h - height * k) / 2 });
  }, []);

  /** Put the drawing's point (`px`, `py`) in the middle of the viewport, at zoom `k`. */
  const centerOn = useCallback((px: number, py: number, k?: number) => {
    const { w, h } = size();
    setView((v) => {
      const kk = clamp(k ?? v.k);
      return { k: kk, x: w / 2 - px * kk, y: h / 2 - py * kk };
    });
  }, []);

  const panBy = useCallback((dx: number, dy: number) => {
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  }, []);

  // The wheel needs a non-passive listener to keep the page from scrolling.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || !interactive) return;
    const onWheel = (e: WheelEvent): void => {
      e.preventDefault();
      const box = el.getBoundingClientRect();
      // Trackpad pinch arrives as ctrl+wheel with small deltas; a mouse wheel as ±100.
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomBy(Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.0015)), { x: e.clientX - box.left, y: e.clientY - box.top });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [interactive, zoomBy]);

  /** Pointer handlers for the viewport: drag on the background (not on a node) pans. */
  const handlers = interactive
    ? {
        onPointerDown: (e: ReactPointerEvent<HTMLDivElement>) => {
          if (e.button !== 0 || (e.target as HTMLElement).closest("button, a, input, textarea")) return;
          drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false };
          e.currentTarget.setPointerCapture?.(e.pointerId);
        },
        onPointerMove: (e: ReactPointerEvent<HTMLDivElement>) => {
          const d = drag.current;
          if (!d || d.id !== e.pointerId) return;
          const dx = e.clientX - d.x;
          const dy = e.clientY - d.y;
          if (!d.moved && Math.hypot(dx, dy) < 3) return;
          d.moved = true;
          d.x = e.clientX;
          d.y = e.clientY;
          panBy(dx, dy);
        },
        onPointerUp: (e: ReactPointerEvent<HTMLDivElement>) => {
          if (drag.current?.id === e.pointerId) drag.current = null;
        },
        onPointerCancel: () => {
          drag.current = null;
        },
      }
    : {};

  return { viewportRef, view, zoomBy, fit, centerOn, panBy, handlers };
}
