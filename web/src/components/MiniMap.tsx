import { useEffect, useMemo, useState } from "react";
import { layoutConversationMap, NODE_H, type MapLayout } from "../conversationMap";
import { usePanZoom } from "../hooks/usePanZoom";
import { readFlag, writeFlag } from "../util";
import type { ConversationState } from "../types";
import { currentNodeKey, MapCanvas } from "./MapCanvas";

interface Props {
  state: ConversationState | null;
  panelBranchId: number | null;
  open: boolean;
  onToggle: () => void;
}

/** Room left around the tree inside the box, in screen pixels. */
const MARGIN = 16;
/** Below this zoom a long tree no longer fits in height: it is shown full width, scrolled to where you are. */
const MIN_K = 0.07;
const SHOWN_KEY = "graftchat.mapPreview";

/** The box around the nodes (the layout's own padding is for the full-screen map). */
function bounds(layout: MapLayout) {
  const xs = layout.nodes.map((n) => n.x);
  const ys = layout.nodes.map((n) => n.y);
  return {
    x0: Math.min(...xs),
    x1: Math.max(...xs),
    y0: Math.min(...ys) - NODE_H / 2,
    y1: Math.max(...ys) + NODE_H / 2,
  };
}

/**
 * The shape of the whole tree, always at the bottom of the sidebar: one dot per prompt in
 * the colour of its branch, "where you are" glowing. It can be folded away; a click opens
 * the map full screen.
 */
export function MiniMap({ state, panelBranchId, open, onToggle }: Props) {
  const layout = useMemo(() => (state ? layoutConversationMap(state) : null), [state]);
  const { viewportRef, view, centerOn } = usePanZoom({ interactive: false, minZoom: 0.01 });
  const currentKey = layout ? currentNodeKey(layout, panelBranchId) : null;
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [shown, setShown] = useState(() => readFlag(SHOWN_KEY, true));
  const empty = !layout || layout.nodes.length === 0;

  const toggleShown = (): void => {
    setShown((v) => {
      writeFlag(SHOWN_KEY, !v);
      return !v;
    });
  };

  // Follow the size of the box (the sidebar can change height).
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [viewportRef, empty, shown]);

  // The whole tree in the box; if it is too long for that, its full width around where you are.
  useEffect(() => {
    const el = viewportRef.current;
    if (!layout || !el || layout.nodes.length === 0 || el.clientWidth === 0) return;
    const b = bounds(layout);
    const w = Math.max(1, el.clientWidth - 2 * MARGIN);
    const h = Math.max(1, el.clientHeight - 2 * MARGIN);
    const kw = w / Math.max(1, b.x1 - b.x0);
    const kh = h / Math.max(1, b.y1 - b.y0);
    const k = Math.min(kw, kh, 0.5);
    const cx = (b.x0 + b.x1) / 2;
    if (k >= MIN_K) {
      centerOn(cx, (b.y0 + b.y1) / 2, k);
      return;
    }
    const kk = Math.max(MIN_K, Math.min(kw, 0.5));
    const node = layout.nodes.find((n) => n.key === currentKey);
    const half = h / 2 / kk;
    const y = Math.min(Math.max(node?.y ?? b.y1, b.y0 + half), b.y1 - half);
    centerOn(cx, y, kk);
  }, [layout, currentKey, size, centerOn, viewportRef]);

  return (
    <div className="map-dock" data-shown={shown ? "" : undefined}>
      <div className="map-dock-head">
        <button
          type="button"
          className="map-dock-toggle"
          aria-expanded={shown}
          aria-label={shown ? "Hide the map preview" : "Show the map preview"}
          onClick={toggleShown}
        >
          <svg className="map-dock-chevron" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <path d="M4 6l4 4 4-4" />
          </svg>
          Map
        </button>
        <button type="button" className="btn btn-small" aria-expanded={open} disabled={empty} onClick={onToggle}>
          {open ? "Close map" : "Open map"}
        </button>
      </div>
      {shown &&
        (empty || !layout ? (
          <p className="map-dock-empty">The map of this chat appears here once you ask something.</p>
        ) : (
          <button
            type="button"
            className="map-dock-view"
            aria-label="Open the conversation map full screen"
            onClick={onToggle}
          >
            <div ref={viewportRef} className="map-viewport map-viewport-mini">
              <MapCanvas layout={layout} view={view} currentKey={currentKey} interactive={false} />
            </div>
          </button>
        ))}
    </div>
  );
}
