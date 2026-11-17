import type { ReactNode } from "react";
import { NODE_W, type MapLayout, type MapNode } from "../conversationMap";
import type { View } from "../hooks/usePanZoom";
import type { BranchStatus } from "../types";

const STATUS_WORD: Record<BranchStatus, string> = {
  open: "open",
  merged: "merged",
  discarded: "discarded",
};

/** How much text a block shows: none from far away, more as one zooms in. */
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
  /** Full screen: nodes are buttons. Sidebar preview: a picture, the whole box is one button. */
  interactive: boolean;
  onNode?: (node: MapNode) => void;
  onBranch?: (branchId: number) => void;
  /** A branch to point out (from the logbook). */
  highlightBranchId?: number | null;
  children?: ReactNode;
}

/** The conversation map drawn at a given pan and zoom (layout: conversationMap.ts). */
export function MapCanvas({
  layout,
  view,
  currentKey,
  interactive,
  onNode,
  onBranch,
  highlightBranchId = null,
}: Props) {
  const current = layout.nodes.find((n) => n.key === currentKey) ?? null;
  const currentBranch = current?.branchId ?? null;

  return (
    <div
      className="map-layer"
      data-zoom={zoomLevel(view.k)}
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
            (e.key === `branch-${currentBranch}`) ||
            (highlightBranchId !== null && e.key === `branch-${highlightBranchId}`);
          return (
            <g key={e.key} data-lane={e.lane ?? undefined} data-status={e.status ?? undefined} data-lit={lit ? "" : undefined}>
              <path d={e.d} className="map-halo" />
              <path d={e.d} className={e.lane === null ? "map-trunk" : "map-edge"} />
            </g>
          );
        })}
      </svg>

      {layout.branchLabels.map((b) => {
        // In the preview the text is drawn by CSS (attr()), so it is not page text twice.
        const content = interactive ? (
          <>
            <span className="map-quote">«{b.quote}»</span>
            <span className="map-status">{STATUS_WORD[b.status]}</span>
          </>
        ) : (
          <>
            <span className="map-quote" data-text={`«${b.quote}»`} />
            <span className="map-status" data-text={STATUS_WORD[b.status]} />
          </>
        );
        const common = {
          className: "map-branch-label",
          style: { left: b.x, top: b.y },
          "data-lane": b.lane,
          "data-status": b.status,
          "data-highlight": highlightBranchId === b.branchId ? "" : undefined,
          title: `«${b.quote}» (${STATUS_WORD[b.status]})`,
        };
        return interactive ? (
          <button
            key={`label-${b.branchId}`}
            type="button"
            {...common}
            aria-label={`Open the branch on «${b.quote}» (${STATUS_WORD[b.status]})`}
            onClick={() => onBranch?.(b.branchId)}
          >
            {content}
          </button>
        ) : (
          <span key={`label-${b.branchId}`} {...common} aria-hidden="true">
            {content}
          </span>
        );
      })}

      {layout.nodes.map((n) => {
        const common = {
          className: `map-node map-node-${n.kind}`,
          style: n.kind === "merge" ? { left: n.x, top: n.y } : { left: n.x, top: n.y, width: NODE_W },
          "data-lane": n.lane ?? undefined,
          "data-status": n.status ?? undefined,
          "data-current": n.key === currentKey ? "" : undefined,
          "data-highlight": highlightBranchId !== null && n.branchId === highlightBranchId ? "" : undefined,
          title: n.full,
        };
        const content = (
          <>
            <Glyph kind={n.kind} />
            {interactive ? (
              <span className="map-label">{n.label}</span>
            ) : (
              <span className="map-label" data-text={n.label} />
            )}
          </>
        );
        return interactive ? (
          <button
            key={n.key}
            type="button"
            {...common}
            aria-label={n.kind === "merge" ? "Go to this merge" : `Go to: ${n.full}`}
            onClick={() => onNode?.(n)}
          >
            {content}
          </button>
        ) : (
          <span key={n.key} {...common} aria-hidden="true">
            {content}
          </span>
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
