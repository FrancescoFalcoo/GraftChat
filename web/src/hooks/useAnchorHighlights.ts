import { useEffect, type RefObject } from "react";
import { findRootByMessageId, offsetsToRange } from "../selection";
import { LANE_COUNT } from "../lanes";
import type { ConversationState } from "../types";

// Minimal typings for the CSS Custom Highlight API, so the code does not depend on
// which version of the DOM library ships them.
type HighlightRegistry = Map<string, unknown>;
type HighlightCtor = new (...ranges: Range[]) => unknown;

const KINDS = ["open", "merged", "discarded", "active"] as const;

/** Every highlight name: one per lane and status (`graft-l0-open` …), "active" = in the panel. */
const NAMES: string[] = [];
for (let lane = 0; lane < LANE_COUNT; lane++) {
  for (const kind of KINDS) NAMES.push(`graft-l${lane}-${kind}`);
}

function highlightApi(): { registry: HighlightRegistry; Highlight: HighlightCtor } | null {
  if (typeof CSS === "undefined") return null;
  const registry = (CSS as unknown as { highlights?: HighlightRegistry }).highlights;
  const Highlight = (globalThis as unknown as { Highlight?: HighlightCtor }).Highlight;
  return registry && typeof Highlight === "function" ? { registry, Highlight } : null;
}

/**
 * Tints the anchored passages of main with the CSS Custom Highlight API
 * (`::highlight(graft-l0-open)` etc., in markdown.css). Progressive enhancement: does nothing where the
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

    const ranges = new Map<string, Range[]>();
    const contents = new Map(state.main.map((m) => [m.id, m.content]));
    state.branches.forEach((branch, index) => {
      const content = contents.get(branch.anchor_message_id);
      const root = findRootByMessageId(scope, branch.anchor_message_id);
      if (content === undefined || !root) return;
      const range = offsetsToRange(root, content, branch.anchor_start, branch.anchor_end);
      if (!range) return;
      const kind = branch.id === activeBranchId ? "active" : branch.status;
      const name = `graft-l${index % LANE_COUNT}-${kind}`;
      const list = ranges.get(name);
      if (list) list.push(range);
      else ranges.set(name, [range]);
    });
    for (const name of NAMES) {
      const list = ranges.get(name);
      if (list) hl.registry.set(name, new hl.Highlight(...list));
      else hl.registry.delete(name);
    }
    return () => {
      for (const name of NAMES) hl.registry.delete(name);
    };
  }, [scopeRef, state, activeBranchId]);
}
