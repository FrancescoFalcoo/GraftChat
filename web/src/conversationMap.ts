/**
 * The conversation map: the tree of one conversation reduced to the prompts the user
 * wrote, the branches they opened and the merges, in the order they happened on main.
 * Pure functions, rendered by components/ConversationMap.tsx.
 */

import { laneOf, plainQuote } from "./lanes";
import type { Branch, BranchStatus, ConversationState } from "./types";
import { truncate } from "./util";

/** Words kept in a node's short label. */
const LABEL_WORDS = 6;
/** Hard limit on a label, in characters, for very long words. */
const LABEL_CHARS = 48;

export interface MapPrompt {
  messageId: number;
  /** Short summary shown on the node: the first words of the prompt. */
  label: string;
  /** The whole prompt, for the tooltip and the accessible name. */
  full: string;
}

export interface MapBranch {
  id: number;
  lane: number;
  status: BranchStatus;
  /** The anchored passage, shortened, without markdown markers. */
  quote: string;
  prompts: MapPrompt[];
}

export type MapRow =
  | { kind: "prompt"; prompt: MapPrompt; branches: MapBranch[] }
  | { kind: "merge"; messageId: number; merged: MapBranch[] };

/** The first words of a prompt, on one line: "Explain grafting in three points…". */
export function shortLabel(text: string): string {
  const words = text.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  if (words.length === 0) return "(empty)";
  const head = words.slice(0, LABEL_WORDS).join(" ");
  const label = truncate(head, LABEL_CHARS);
  return words.length > LABEL_WORDS && !label.endsWith("…") ? `${label}…` : label;
}

function prompt(messageId: number, content: string): MapPrompt {
  return { messageId, label: shortLabel(content), full: content };
}

function mapBranch(state: ConversationState, branch: Branch): MapBranch {
  return {
    id: branch.id,
    lane: laneOf(state.branches, branch.id),
    status: branch.status,
    quote: truncate(plainQuote(branch.anchor_quote), 40),
    prompts: branch.messages.filter((m) => m.role === "user").map((m) => prompt(m.id, m.content)),
  };
}

/**
 * Rows of the map, in main order. A branch hangs under the prompt whose answer it is
 * anchored to; a merge row lists the branches merged at that node.
 */
export function buildConversationMap(state: ConversationState): MapRow[] {
  const rows: MapRow[] = [];
  let lastPrompt: Extract<MapRow, { kind: "prompt" }> | null = null;

  for (const m of state.main) {
    if (m.role === "user") {
      lastPrompt = { kind: "prompt", prompt: prompt(m.id, m.content), branches: [] };
      rows.push(lastPrompt);
    } else if (m.role === "assistant") {
      const anchored = state.branches.filter((b) => b.anchor_message_id === m.id);
      if (anchored.length > 0 && lastPrompt) {
        lastPrompt.branches.push(...anchored.map((b) => mapBranch(state, b)));
      }
    } else {
      const merged = state.branches.filter((b) => b.merge_message_id === m.id);
      rows.push({ kind: "merge", messageId: m.id, merged: merged.map((b) => mapBranch(state, b)) });
    }
  }
  return rows;
}
