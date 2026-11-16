import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { findAnchorRoot, rangeToSelection, type AnchorSelection } from "../selection";

interface Props {
  /** Element containing the main thread; selections elsewhere are ignored. */
  scopeRef: RefObject<HTMLElement>;
  /** Raw content of an assistant message of main, or null if the id is not one. */
  contentOf: (messageId: number) => string | null;
  onOpen: (messageId: number, selection: AnchorSelection) => Promise<boolean>;
}

interface Found {
  messageId: number;
  selection: AnchorSelection;
  top: number;
  left: number;
}

const BUTTON_WIDTH = 132;
const BUTTON_HEIGHT = 34;

/** The current window selection as a branch anchor, when it is a valid one. */
function readSelection(
  scope: HTMLElement,
  contentOf: (messageId: number) => string | null,
): Found | null {
  const sel = document.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const found = findAnchorRoot(sel.getRangeAt(0), scope);
  if (!found) return null;
  const messageId = Number(found.root.dataset.msgId);
  const content = Number.isInteger(messageId) ? contentOf(messageId) : null;
  if (content === null) return null;
  const selection = rangeToSelection(found.root, found.range, content);
  if (!selection) return null;

  const rect =
    typeof found.range.getBoundingClientRect === "function"
      ? found.range.getBoundingClientRect()
      : { top: 0, bottom: 0, left: 0, width: 0 };
  if (rect.bottom < 0 || rect.top > window.innerHeight) return null;
  const above = rect.top - BUTTON_HEIGHT - 8;
  const top = above < 8 ? rect.bottom + 8 : above;
  const centred = rect.left + rect.width / 2 - BUTTON_WIDTH / 2;
  const left = Math.max(8, Math.min(centred, window.innerWidth - BUTTON_WIDTH - 8));
  return { messageId, selection, top, left };
}

/** Floating "Open branch" button shown next to a valid selection. */
export function SelectionPopover({ scopeRef, contentOf, onOpen }: Props) {
  const [found, setFound] = useState<Found | null>(null);
  const [busy, setBusy] = useState(false);
  const mouseDown = useRef(false);

  const update = useCallback(() => {
    const scope = scopeRef.current;
    setFound(scope ? readSelection(scope, contentOf) : null);
  }, [scopeRef, contentOf]);

  useEffect(() => {
    const onSelectionChange = (): void => {
      // While dragging, wait for the mouse to be released before showing the button.
      if (mouseDown.current) setFound(null);
      else update();
    };
    const onMouseDown = (e: MouseEvent): void => {
      const target = e.target instanceof Element ? e.target : null;
      if (!target?.closest(".open-branch-btn")) mouseDown.current = true;
    };
    const onMouseUp = (): void => {
      mouseDown.current = false;
      window.setTimeout(update, 0);
    };
    document.addEventListener("selectionchange", onSelectionChange);
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("mouseup", onMouseUp);
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      document.removeEventListener("selectionchange", onSelectionChange);
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [update]);

  if (!found) return null;

  const open = async (): Promise<void> => {
    if (busy) return;
    setBusy(true);
    const ok = await onOpen(found.messageId, found.selection);
    setBusy(false);
    if (ok) {
      document.getSelection()?.removeAllRanges();
      setFound(null);
    }
  };

  return (
    <button
      type="button"
      className="open-branch-btn"
      style={{ top: found.top, left: found.left, width: BUTTON_WIDTH, height: BUTTON_HEIGHT }}
      disabled={busy}
      // Keep the text selection alive: a normal mousedown would clear it before the click.
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => void open()}
    >
      <span aria-hidden="true">⑂</span> {busy ? "Opening…" : "Open branch"}
    </button>
  );
}
