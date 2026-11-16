import { useEffect, type RefObject } from "react";
import { findRootByMessageId, offsetsToRange } from "../selection";
import type { ConversationState } from "../types";

// Minimal typings for the CSS Custom Highlight API, so the code does not depend on
// which version of the DOM library ships them.
type HighlightRegistry = Map<string, unknown>;
type HighlightCtor = new (...ranges: Range[]) => unknown;

const GROUPS = ["open", "merged", "discarded", "active"] as const;
type Group = (typeof GROUPS)[number];

function highlightApi(): { registry: HighlightRegistry; Highlight: HighlightCtor } | null {
  if (typeof CSS === "undefined") return null;
  const registry = (CSS as unknown as { highlights?: HighlightRegistry }).highlights;
  const Highlight = (globalThis as unknown as { Highlight?: HighlightCtor }).Highlight;
  return registry && typeof Highlight === "function" ? { registry, Highlight } : null;
}

/**
 * Tints the anchored passages of main with the CSS Custom Highlight API
 * (`::highlight(graft-open)` etc.). Progressive enhancement: does nothing where the
 * API is missing; the chips under each message carry the same information.
 */
export function useAnchorHighlights(
  scopeRef: RefObject<HTMLElement>,
  state: ConversationState | null,
  activeBranchId: number | null,
): void {
  useEffect(() => {
    const hl = highlightApi();
    const scope = scopeRef.current;
    if (!hl || !scope || !state) return;

    const ranges: Record<Group, Range[]> = { open: [], merged: [], discarded: [], active: [] };
    const contents = new Map(state.main.map((m) => [m.id, m.content]));
    for (const branch of state.branches) {
      const content = contents.get(branch.anchor_message_id);
      const root = findRootByMessageId(scope, branch.anchor_message_id);
      if (content === undefined || !root) continue;
      const range = offsetsToRange(root, content, branch.anchor_start, branch.anchor_end);
      if (range) ranges[branch.id === activeBranchId ? "active" : branch.status].push(range);
    }
    for (const group of GROUPS) {
      const name = `graft-${group}`;
      if (ranges[group].length > 0) hl.registry.set(name, new hl.Highlight(...ranges[group]));
      else hl.registry.delete(name);
    }
    return () => {
      for (const group of GROUPS) hl.registry.delete(`graft-${group}`);
    };
  }, [scopeRef, state, activeBranchId]);
}
