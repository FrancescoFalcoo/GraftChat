import { useEffect, useMemo, useState } from "react";
import { layoutConversationMap } from "../conversationMap";
import { usePanZoom } from "../hooks/usePanZoom";
import type { ConversationState } from "../types";
import { currentNodeKey, MapCanvas } from "./MapCanvas";

interface Props {
  state: ConversationState | null;
  panelBranchId: number | null;
  open: boolean;
  onToggle: () => void;
}

/** Zoom of the preview: small enough to show the neighbourhood, large enough to see shapes. */
const PREVIEW_K = 0.3;

/**
 * The map, always visible at the bottom of the sidebar, centred on where you are. It
 * follows the conversation and the open branch; a click opens it full screen.
 */
export function MiniMap({ state, panelBranchId, open, onToggle }: Props) {
  const layout = useMemo(() => (state ? layoutConversationMap(state) : null), [state]);
  const { viewportRef, view, fit, centerOn } = usePanZoom({ interactive: false });
  const currentKey = layout ? currentNodeKey(layout, panelBranchId) : null;
  const [size, setSize] = useState({ w: 0, h: 0 });
  const empty = !layout || layout.nodes.length === 0;

  // Follow the size of the box (the sidebar can change height).
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [viewportRef, empty]);

  // Re-centre when the conversation, the open branch or the box changes.
  useEffect(() => {
    const el = viewportRef.current;
    if (!layout || !el || layout.nodes.length === 0) return;
    const k = Math.min(el.clientWidth / layout.width, el.clientHeight / layout.height);
    if (k >= PREVIEW_K) {
      fit(layout.width, layout.height, 0.6);
      return;
    }
    const node = layout.nodes.find((n) => n.key === currentKey);
    if (!node) return;
    // Halfway between where you are and the trunk: a side branch keeps main in sight.
    const trunkX = layout.nodes.find((n) => n.branchId === null)?.x ?? node.x;
    centerOn((node.x + trunkX) / 2, node.y, PREVIEW_K);
  }, [layout, currentKey, size, fit, centerOn, viewportRef]);

  return (
    <div className="map-dock">
      <div className="map-dock-head">
        <span className="map-dock-name">Map</span>
        <button
          type="button"
          className="btn btn-small"
          aria-expanded={open}
          disabled={empty}
          onClick={onToggle}
        >
          {open ? "Close map" : "Open map"}
        </button>
      </div>
      {empty || !layout ? (
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
      )}
    </div>
  );
}
