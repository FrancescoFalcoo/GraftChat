import { useEffect, useRef, type RefObject } from "react";
import { plainQuote } from "../lanes";
import { highlightName } from "./useAnchorHighlights";
import { offsetsToRange } from "../selection";
import type { ConversationState } from "../types";

/** Delay before a click opens a branch, so a double click (select a word) can cancel it. */
const CLICK_DELAY_MS = 260;

type HighlightRegistry = Map<string, unknown>;
type HighlightInstance = { priority: number };
type HighlightCtor = new (...ranges: Range[]) => HighlightInstance;

export interface AnchorCandidate {
  branchId: number;
  /** Length of the anchored passage: the shortest one wins when passages overlap. */
  length: number;
  /** Creation order: the most recent one wins a tie. */
  order: number;
  rects: { left: number; right: number; top: number; bottom: number }[];
}

/** The branch whose passage is under the point, or null. */
export function pickAnchorAt(candidates: AnchorCandidate[], x: number, y: number): number | null {
  let best: AnchorCandidate | null = null;
  for (const c of candidates) {
    const hit = c.rects.some((r) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom);
    if (!hit) continue;
    if (!best || c.length < best.length || (c.length === best.length && c.order > best.order)) best = c;
  }
  return best?.branchId ?? null;
}

interface Hit {
  branchId: number;
  root: HTMLElement;
  range: Range;
  quote: string;
}

/**
 * Makes the anchored passages of main clickable: under the pointer a passage shows a
 * pointer cursor, a stronger tint and a tooltip; a click (not a drag, not a double
 * click) opens its branch in the side panel.
 */
export function useAnchorClicks(
  scopeRef: RefObject<HTMLElement>,
  state: ConversationState | null,
  onOpenBranch: (branchId: number) => void,
): void {
  const openRef = useRef(onOpenBranch);
  openRef.current = onOpenBranch;

  useEffect(() => {
    const scope = scopeRef.current;
    if (!scope || !state) return;

    const registry = (globalThis.CSS as unknown as { highlights?: HighlightRegistry } | undefined)
      ?.highlights;
    const Highlight = (globalThis as unknown as { Highlight?: HighlightCtor }).Highlight;

    const hitAt = (target: EventTarget | null, x: number, y: number): Hit | null => {
      const el = target instanceof Element ? target : null;
      const root = el?.closest<HTMLElement>("[data-anchor-root]");
      if (!root || !scope.contains(root)) return null;
      const messageId = Number(root.dataset.msgId);
      const content = state.main.find((m) => m.id === messageId)?.content;
      if (content === undefined) return null;

      const ranges = new Map<number, Range>();
      const candidates: AnchorCandidate[] = [];
      state.branches.forEach((b, order) => {
        if (b.anchor_message_id !== messageId) return;
        const range = offsetsToRange(root, content, b.anchor_start, b.anchor_end);
        if (!range || typeof range.getClientRects !== "function") return;
        ranges.set(b.id, range);
        candidates.push({
          branchId: b.id,
          length: b.anchor_end - b.anchor_start,
          order,
          rects: Array.from(range.getClientRects()),
        });
      });
      const branchId = pickAnchorAt(candidates, x, y);
      if (branchId === null) return null;
      const branch = state.branches.find((b) => b.id === branchId)!;
      return {
        branchId,
        root,
        range: ranges.get(branchId)!,
        quote: plainQuote(branch.anchor_quote),
      };
    };

    let hovered: Hit | null = null;
    const clearHover = (): void => {
      if (!hovered) return;
      hovered.root.classList.remove("anchor-hover");
      hovered.root.removeAttribute("title");
      registry?.delete(highlightName(hovered.branchId, "hover"));
      hovered = null;
    };
    const setHover = (hit: Hit | null): void => {
      if (hit && hovered && hit.branchId === hovered.branchId) return;
      clearHover();
      if (!hit) return;
      hovered = hit;
      hit.root.classList.add("anchor-hover");
      hit.root.title = `Click to open the branch on «${hit.quote}»`;
      if (registry && Highlight) {
        const highlight = new Highlight(hit.range);
        highlight.priority = 1; // above the status tint
        registry.set(highlightName(hit.branchId, "hover"), highlight);
      }
    };

    let frame = 0;
    const onMove = (e: MouseEvent): void => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setHover(hitAt(e.target, e.clientX, e.clientY)));
    };
    const onLeave = (): void => {
      cancelAnimationFrame(frame);
      clearHover();
    };

    let timer = 0;
    const selectionIsEmpty = (): boolean => window.getSelection()?.isCollapsed ?? true;
    const onClick = (e: MouseEvent): void => {
      window.clearTimeout(timer);
      if (e.button !== 0 || e.detail > 1 || !selectionIsEmpty()) return;
      const hit = hitAt(e.target, e.clientX, e.clientY);
      if (!hit) return;
      timer = window.setTimeout(() => {
        if (selectionIsEmpty()) openRef.current(hit.branchId);
      }, CLICK_DELAY_MS);
    };
    const onDoubleClick = (): void => window.clearTimeout(timer);

    scope.addEventListener("mousemove", onMove);
    scope.addEventListener("mouseleave", onLeave);
    scope.addEventListener("click", onClick);
    scope.addEventListener("dblclick", onDoubleClick);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      clearHover();
      scope.removeEventListener("mousemove", onMove);
      scope.removeEventListener("mouseleave", onLeave);
      scope.removeEventListener("click", onClick);
      scope.removeEventListener("dblclick", onDoubleClick);
    };
  }, [scopeRef, state]);
}
