import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { layoutConversationMap, type MapNode } from "../conversationMap";
import { usePanZoom } from "../hooks/usePanZoom";
import { buildLogbook, logbookSummary } from "../logbook";
import type { ConversationState } from "../types";
import { readFlag, writeFlag } from "../util";
import { Logbook } from "./Logbook";
import { currentNodeKey, MapCanvas } from "./MapCanvas";
import { NodeDetails } from "./NodeDetails";

interface Props {
  state: ConversationState;
  /** The branch open in the side panel, if any: "where you are". */
  panelBranchId?: number | null;
  /** Go to a message: `branchId` null = a message on main. */
  onJump: (messageId: number, branchId: number | null) => void;
  /** Open a branch in the side panel. */
  onOpenBranch: (branchId: number) => void;
  onClose: () => void;
}

const STEP = 1.25;
const LOGBOOK_KEY = "graftchat.logbookOpen";

/**
 * The whole tree of the current conversation, full screen. On the left: what it is and the
 * logbook. On the right: the tree, its zoom bottom right; a click on a block opens its details, and
 * only from there one goes to it. Ways out: "Back to chat" and "Close map" on the left, ×
 * top right, Escape.
 */
export function ConversationMap({ state, panelBranchId = null, onJump, onOpenBranch, onClose }: Props) {
  const layout = useMemo(() => layoutConversationMap(state), [state]);
  const logbook = useMemo(() => buildLogbook(state), [state]);
  const currentKey = currentNodeKey(layout, panelBranchId);
  const { viewportRef, view, zoomBy, fit, centerOn, panBy, handlers } = usePanZoom({ interactive: true });
  const [highlight, setHighlight] = useState<number | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const [logShown, setLogShown] = useState(() => readFlag(LOGBOOK_KEY, true));
  const showLog = (on: boolean): void => {
    writeFlag(LOGBOOK_KEY, on);
    setLogShown(on);
  };
  const selected = layout.nodes.find((n) => n.key === selectedKey) ?? null;

  const showCurrent = (): void => {
    const node = layout.nodes.find((n) => n.key === currentKey);
    if (node) centerOn(node.x, node.y, Math.max(view.k, 0.9));
  };

  // First view, once: the whole tree if it is readable that way, otherwise where you are.
  // (A reply arriving while the map is open must not move the view under the pointer.)
  const placed = useRef(false);
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (placed.current || !el || layout.nodes.length === 0) return;
    placed.current = true;
    const k = Math.min(el.clientWidth / layout.width, el.clientHeight / layout.height);
    if (k >= 0.6) fit(layout.width, layout.height, 1);
    else {
      const node = layout.nodes.find((n) => n.key === currentKey);
      if (node) centerOn(node.x, node.y, 0.9);
    }
  }, [layout, currentKey, fit, centerOn, viewportRef]);

  useEffect(() => {
    backRef.current?.focus();
  }, []);

  // Folding or unfolding the logbook changes the width of the tree's box: keep in the middle
  // what was in the middle, so the tree does not slide under the title card.
  const lastWidth = useRef<number | null>(null);
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    if (lastWidth.current !== null && lastWidth.current !== el.clientWidth) {
      panBy((el.clientWidth - lastWidth.current) / 2, 0);
    }
    lastWidth.current = el.clientWidth;
  }, [logShown, panBy, viewportRef]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (selectedKey !== null) setSelectedKey(null); // first the details, then the map
      else onClose();
      return;
    }
    if ((e.target as HTMLElement).closest("input, textarea")) return;
    const pan: Record<string, [number, number]> = {
      ArrowLeft: [80, 0],
      ArrowRight: [-80, 0],
      ArrowUp: [0, 80],
      ArrowDown: [0, -80],
    };
    if (e.key === "+" || e.key === "=") zoomBy(STEP);
    else if (e.key === "-" || e.key === "_") zoomBy(1 / STEP);
    else if (e.key === "0") fit(layout.width, layout.height, 1);
    else if (pan[e.key] && (e.target as HTMLElement).classList.contains("map-viewport")) panBy(...pan[e.key]);
    else return;
    e.preventDefault();
  };

  const showBranch = (branchId: number): void => {
    setHighlight(branchId);
    const first = layout.nodes.find((n) => n.branchId === branchId);
    if (first) centerOn(first.x, first.y, Math.max(view.k, 0.8));
  };

  const visit = (n: MapNode): void => {
    if (n.messageId !== null) onJump(n.messageId, n.branchId);
    else if (n.branchId !== null) onOpenBranch(n.branchId);
  };

  return (
    <div
      className="map-screen"
      data-logbook={logShown ? "open" : "folded"}
      role="dialog"
      aria-modal="true"
      aria-label="Conversation map"
      onKeyDown={onKeyDown}
    >
      <aside className="map-side" aria-label="About this map">
        <button ref={backRef} type="button" className="btn btn-small map-back" onClick={onClose}>
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Back to chat
        </button>

        <header className="map-head">
          <h2 className="map-title">{state.conversation.title}</h2>
          <p className="map-sub">
            {logbook.prompts} prompt{logbook.prompts === 1 ? "" : "s"} on main, {state.branches.length} branch
            {state.branches.length === 1 ? "" : "es"}
          </p>
        </header>

        {logShown ? (
          <>
            <div className="map-side-scroll">
              <Logbook
                logbook={logbook}
                onShowBranch={showBranch}
                onOpenBranch={onOpenBranch}
                onJump={(id) => onJump(id, null)}
                onFold={() => showLog(false)}
              />
            </div>

            <button type="button" className="btn map-close" onClick={onClose}>
              Close map
            </button>
          </>
        ) : (
          <button type="button" className="btn map-log-open" aria-expanded="false" onClick={() => showLog(true)}>
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            Logbook
            <span className="map-log-meta">{logbookSummary(logbook)}</span>
          </button>
        )}
      </aside>

      <div
        ref={viewportRef}
        className="map-viewport"
        tabIndex={0}
        aria-label="Map canvas: drag to move, wheel or + and − to zoom, 0 to fit"
        {...handlers}
      >
        {layout.nodes.length === 0 ? (
          <p className="map-empty">Nothing here yet. Ask something first.</p>
        ) : (
          <MapCanvas
            layout={layout}
            view={view}
            currentKey={currentKey}
            interactive
            selectedKey={selectedKey}
            highlightBranchId={highlight}
            onSelect={(n) => setSelectedKey((key) => (key === n.key ? null : n.key))}
          />
        )}
      </div>

      <div className="map-toolbar" role="group" aria-label="View">
        <p className="map-hint">Drag to move, wheel to zoom, click a block for its details.</p>
        <div className="map-toolbar-row">
          <div className="map-zoom" role="group" aria-label="Zoom">
            <button type="button" className="btn btn-small" aria-label="Zoom out" onClick={() => zoomBy(1 / STEP)}>
              −
            </button>
            <output className="map-zoom-value" aria-live="polite">
              {Math.round(view.k * 100)}%
            </output>
            <button type="button" className="btn btn-small" aria-label="Zoom in" onClick={() => zoomBy(STEP)}>
              +
            </button>
          </div>
          <button type="button" className="btn btn-small" onClick={() => fit(layout.width, layout.height, 1)}>
            Fit
          </button>
          <button type="button" className="btn btn-small" onClick={showCurrent} disabled={currentKey === null}>
            Where I am
          </button>
        </div>
      </div>

      <button type="button" className="icon-btn map-x" aria-label="Close map" onClick={onClose}>
        <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>

      {selected && (
        <NodeDetails
          node={selected}
          state={state}
          onVisit={visit}
          onOpenBranch={onOpenBranch}
          onClose={() => setSelectedKey(null)}
        />
      )}
    </div>
  );
}
