import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { layoutConversationMap, type MapNode } from "../conversationMap";
import { usePanZoom } from "../hooks/usePanZoom";
import { buildLogbook } from "../logbook";
import type { ConversationState } from "../types";
import { Logbook } from "./Logbook";
import { currentNodeKey, MapCanvas } from "./MapCanvas";

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

const LOGBOOK_KEY = "graftchat.logbookOpen";
const STEP = 1.25;

function loadLogbookOpen(): boolean {
  try {
    return window.localStorage.getItem(LOGBOOK_KEY) !== "0";
  } catch {
    return true;
  }
}

/** The whole tree of the current conversation, full screen, with its logbook. */
export function ConversationMap({ state, panelBranchId = null, onJump, onOpenBranch, onClose }: Props) {
  const layout = useMemo(() => layoutConversationMap(state), [state]);
  const logbook = useMemo(() => buildLogbook(state), [state]);
  const currentKey = currentNodeKey(layout, panelBranchId);
  const { viewportRef, view, zoomBy, fit, centerOn, panBy, handlers } = usePanZoom({ interactive: true });
  const [logOpen, setLogOpen] = useState(loadLogbookOpen);
  const [highlight, setHighlight] = useState<number | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

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
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(LOGBOOK_KEY, logOpen ? "1" : "0");
    } catch {
      // per-browser convenience only
    }
  }, [logOpen]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
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
    const label = layout.branchLabels.find((b) => b.branchId === branchId);
    if (label) centerOn(label.x, label.y + 60, Math.max(view.k, 0.8));
  };

  const jumpNode = (n: MapNode): void => {
    if (n.messageId !== null) onJump(n.messageId, n.branchId);
    else if (n.branchId !== null) onOpenBranch(n.branchId);
  };

  return (
    <div
      className="map-screen"
      role="dialog"
      aria-modal="true"
      aria-label="Conversation map"
      onKeyDown={onKeyDown}
      data-log={logOpen ? "open" : "closed"}
    >
      <header className="map-head">
        <h2 className="map-title">{state.conversation.title}</h2>
        <p className="map-sub">
          {logbook.prompts} prompt{logbook.prompts === 1 ? "" : "s"} on main, {state.branches.length} branch
          {state.branches.length === 1 ? "" : "es"}
        </p>
      </header>

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
            highlightBranchId={highlight}
            onNode={jumpNode}
            onBranch={onOpenBranch}
          />
        )}
      </div>

      <div className="map-controls">
        <button ref={closeRef} type="button" className="btn map-close" onClick={onClose}>
          Close map
        </button>
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

      <button
        type="button"
        className="btn btn-small map-log-toggle"
        aria-expanded={logOpen}
        aria-controls="map-logbook"
        onClick={() => setLogOpen((v) => !v)}
      >
        {logOpen ? "Hide logbook" : "Logbook"}
      </button>
      {logOpen && (
        <aside className="map-log" id="map-logbook" aria-label="Logbook">
          <h2 className="map-log-title">Logbook</h2>
          <Logbook
            logbook={logbook}
            onShowBranch={showBranch}
            onOpenBranch={onOpenBranch}
            onJump={(id) => onJump(id, null)}
          />
        </aside>
      )}
    </div>
  );
}
