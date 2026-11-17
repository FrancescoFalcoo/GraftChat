import { NODE_W, type MapLayout, type MapNode } from "../conversationMap";
import type { View } from "../hooks/usePanZoom";

/** How much text a block shows: none from far away, a little more when close. */
export function zoomLevel(k: number): "far" | "mid" | "near" {
  if (k < 0.55) return "far";
  if (k < 1.25) return "mid";
  return "near";
}

function Glyph({ kind }: { kind: MapNode["kind"] }) {
  // Prompt: a speech mark. Merge: two stems joining into one. Empty: an open ring.
  const path =
    kind === "merge"
      ? "M4 2.5v3.2c0 2 1.6 3.3 4 3.3s4-1.3 4-3.3V2.5M8 9v4.5"
      : kind === "empty"
        ? "M8 3a5 5 0 1 1 0 10A5 5 0 0 1 8 3"
        : "M3 4.5c0-1.1.9-2 2-2h6c1.1 0 2 .9 2 2v4c0 1.1-.9 2-2 2H7.2L4.5 13v-2.5H5c-1.1 0-2-.9-2-2z";
  return (
    <svg className="map-glyph" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d={path} strokeDasharray={kind === "empty" ? "2.2 2" : undefined} />
    </svg>
  );
}

interface Props {
  layout: MapLayout;
  view: View;
  /** The node that is "where you are": it carries the glow. */
  currentKey: string | null;
  /**
   * Full screen: blocks with their essential text, selectable. Sidebar preview: only the
   * shape of the tree, a coloured dot per node.
   */
  interactive: boolean;
  /** The block whose details are open. */
  selectedKey?: string | null;
  onSelect?: (node: MapNode) => void;
  /** A branch to point out (from the logbook). */
  highlightBranchId?: number | null;
}

/** The conversation map drawn at a given pan and zoom (layout: conversationMap.ts). */
export function MapCanvas({
  layout,
  view,
  currentKey,
  interactive,
  selectedKey = null,
  onSelect,
  highlightBranchId = null,
}: Props) {
  const current = layout.nodes.find((n) => n.key === currentKey) ?? null;
  const currentBranch = current?.branchId ?? null;

  return (
    <div
      className="map-layer"
      data-zoom={interactive ? zoomLevel(view.k) : "dots"}
      style={{
        width: layout.width,
        height: layout.height,
        transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
      }}
    >
      <svg className="map-edges" width={layout.width} height={layout.height} aria-hidden="true">
        {layout.edges.map((e) => {
          const lit =
            (e.lane === null && currentBranch === null) ||
            e.key === `branch-${currentBranch}` ||
            (highlightBranchId !== null && e.key === `branch-${highlightBranchId}`);
          return (
            <g key={e.key} data-lane={e.lane ?? undefined} data-status={e.status ?? undefined} data-lit={lit ? "" : undefined}>
              <path d={e.d} className="map-halo" />
              <path d={e.d} className={e.lane === null ? "map-trunk" : "map-edge"} />
            </g>
          );
        })}
      </svg>

      {layout.nodes.map((n) => {
        const marks = {
          "data-lane": n.lane ?? undefined,
          "data-status": n.status ?? undefined,
          "data-current": n.key === currentKey ? "" : undefined,
        };
        if (!interactive) {
          return (
            <span
              key={n.key}
              className={`map-dot map-dot-${n.kind}`}
              style={{ left: n.x, top: n.y }}
              aria-hidden="true"
              {...marks}
            />
          );
        }
        const name =
          n.kind === "merge"
            ? "Merge"
            : n.kind === "empty"
              ? `Branch on «${n.quote}», no messages yet`
              : n.full;
        return (
          <button
            key={n.key}
            type="button"
            className={`map-node map-node-${n.kind}`}
            style={n.kind === "merge" ? { left: n.x, top: n.y } : { left: n.x, top: n.y, width: NODE_W }}
            {...marks}
            data-selected={n.key === selectedKey ? "" : undefined}
            data-highlight={highlightBranchId !== null && n.branchId === highlightBranchId ? "" : undefined}
            aria-pressed={n.key === selectedKey}
            aria-label={`Details: ${name}`}
            onClick={() => onSelect?.(n)}
          >
            <Glyph kind={n.kind} />
            <span className="map-node-text">
              {n.quote !== null && n.kind === "prompt" && <span className="map-node-quote">«{n.quote}»</span>}
              <span className="map-label">{n.kind === "empty" ? `«${n.quote}»` : n.label}</span>
              {n.kind === "empty" && <span className="map-node-note">No messages yet</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** "Where you are": the last prompt of the open branch, or the last node of main. */
export function currentNodeKey(layout: MapLayout, panelBranchId: number | null): string | null {
  if (panelBranchId !== null) {
    const own = layout.nodes.filter((n) => n.branchId === panelBranchId);
    if (own.length > 0) return own[own.length - 1].key;
  }
  const main = layout.nodes.filter((n) => n.branchId === null);
  return main.length > 0 ? main[main.length - 1].key : null;
}
