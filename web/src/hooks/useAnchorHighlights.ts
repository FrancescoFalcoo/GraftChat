import { useEffect, type RefObject } from "react";
import { findRootByMessageId, offsetsToRange } from "../selection";
import { branchColors } from "../lanes";
import type { ConversationState } from "../types";

// Minimal typings for the CSS Custom Highlight API, so the code does not depend on
// which version of the DOM library ships them.
type HighlightRegistry = Map<string, unknown>;
type HighlightCtor = new (...ranges: Range[]) => unknown;

const STYLE_ID = "graft-highlight-rules";

function highlightApi(): { registry: HighlightRegistry; Highlight: HighlightCtor } | null {
  if (typeof CSS === "undefined") return null;
  const registry = (CSS as unknown as { highlights?: HighlightRegistry }).highlights;
  const Highlight = (globalThis as unknown as { Highlight?: HighlightCtor }).Highlight;
  return registry && typeof Highlight === "function" ? { registry, Highlight } : null;
}

/** Highlight name of a branch's passage: `graft-b12` (status tint), `-active`, `-hover`. */
export function highlightName(branchId: number, kind: "" | "active" | "hover" = ""): string {
  return kind ? `graft-b${branchId}-${kind}` : `graft-b${branchId}`;
}

const tint = (color: string, pct: number): string =>
  `color-mix(in srgb, ${color} ${pct}%, transparent)`;

/**
 * `::highlight()` rules cannot read per-element custom properties, so each branch gets
 * its own rules, generated from its colour: open = 20% tint + 2px underline; merged =
 * underline only; discarded = dashed muted underline; active (in the side panel) and
 * hover are stronger.
 */
export function highlightRules(state: ConversationState): string {
  const colors = branchColors(state.branches);
  const rules: string[] = [];
  for (const b of state.branches) {
    const c = colors.get(b.id)!;
    const name = highlightName(b.id);
    if (b.status === "open") {
      rules.push(`::highlight(${name}) { background-color: ${tint(c, 20)}; text-decoration: underline solid ${c} 2px; }`);
    } else if (b.status === "merged") {
      rules.push(`::highlight(${name}) { text-decoration: underline solid ${c} 2px; }`);
    } else {
      rules.push(`::highlight(${name}) { text-decoration: underline dashed var(--muted) 1px; }`);
    }
    rules.push(
      `::highlight(${highlightName(b.id, "active")}) { background-color: ${tint(c, 34)}; text-decoration: underline solid ${c} 2px; }`,
      `::highlight(${highlightName(b.id, "hover")}) { background-color: ${tint(c, 45)}; text-decoration: underline solid ${c} 3px; }`,
    );
  }
  return rules.join("\n");
}

/**
 * Tints the anchored passages of main with the CSS Custom Highlight API, one highlight
 * per branch in its own colour. Progressive enhancement: does nothing where the API is
 * missing; the chips under each message carry the same information.
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

    let style = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
    if (!style) {
      style = document.createElement("style");
      style.id = STYLE_ID;
      document.head.appendChild(style);
    }
    style.textContent = highlightRules(state);

    const contents = new Map(state.main.map((m) => [m.id, m.content]));
    const names: string[] = [];
    for (const branch of state.branches) {
      const content = contents.get(branch.anchor_message_id);
      const root = findRootByMessageId(scope, branch.anchor_message_id);
      if (content === undefined || !root) continue;
      const range = offsetsToRange(root, content, branch.anchor_start, branch.anchor_end);
      if (!range) continue;
      const name = highlightName(branch.id, branch.id === activeBranchId ? "active" : "");
      hl.registry.set(name, new hl.Highlight(range));
      names.push(name);
    }
    return () => {
      for (const name of names) hl.registry.delete(name);
    };
  }, [scopeRef, state, activeBranchId]);
}
