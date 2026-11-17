/**
 * The conversation map: the tree of one conversation drawn as a graph.
 *
 * Main is a vertical trunk with one node per prompt and per merge. Every branch leaves
 * the trunk at the prompt whose answer it is anchored to, runs down its own column with
 * one node per prompt, and, if it was merged, comes back into the trunk at its merge
 * node. Pure layout: components/MapCanvas.tsx draws the result, in the sidebar and full
 * screen.
 */

import { laneOf, plainQuote } from "./lanes";
import type { BranchStatus, ConversationState } from "./types";
import { truncate } from "./util";

/** Words kept in a node's short label. */
const LABEL_WORDS = 5;
/** Hard limit on a label, in characters. */
const LABEL_CHARS = 30;

/** Grid of the drawing, in pixels (at zoom 1). Nodes are blocks centred on their point. */
export const ROW_H = 96;
export const COL_W = 248;
export const PAD = 140;
/** Size of a node's block, and the longest text it carries (CSS shows as many lines as fit). */
export const NODE_W = 208;
export const NODE_H = 60;
const NODE_TEXT = 220;

/** The first words of a prompt, on one line: "Explain grafting in three points…". */
export function shortLabel(text: string): string {
  const words = text.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  if (words.length === 0) return "(empty)";
  // Whole words while they fit; a single word longer than the limit is cut.
  let label = "";
  let used = 0;
  for (const word of words.slice(0, LABEL_WORDS)) {
    const next = label ? `${label} ${word}` : word;
    if (Array.from(next).length > LABEL_CHARS) break;
    label = next;
    used++;
  }
  if (!label) return truncate(words[0], LABEL_CHARS);
  return used < words.length ? `${label}…` : label;
}

export interface MapNode {
  /** Unique key for rendering. */
  key: string;
  kind: "prompt" | "merge" | "empty";
  x: number;
  y: number;
  label: string;
  /** Tooltip and accessible name. */
  full: string;
  /** Message to show when the node is clicked (null for an empty branch). */
  messageId: number | null;
  /** null = main. */
  branchId: number | null;
  lane: number | null;
  status: BranchStatus | null;
}

export interface MapEdge {
  key: string;
  /** SVG path. */
  d: string;
  /** null = the trunk. */
  lane: number | null;
  status: BranchStatus | null;
}

export interface MapBranchLabel {
  branchId: number;
  lane: number;
  status: BranchStatus;
  quote: string;
  /** Where the branch leaves the trunk: halfway along its first curve. */
  x: number;
  y: number;
}

/** The text of a node: the whole prompt on one line, cut only when very long. */
function nodeText(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat ? truncate(flat, NODE_TEXT) : "(empty)";
}

export interface MapLayout {
  width: number;
  height: number;
  nodes: MapNode[];
  edges: MapEdge[];
  branchLabels: MapBranchLabel[];
}

interface MainNode {
  kind: "prompt" | "merge";
  messageId: number;
  content: string;
}

interface BranchPlan {
  id: number;
  lane: number;
  status: BranchStatus;
  quote: string;
  anchor: number; // index in mainNodes
  merge: number | null; // index in mainNodes
  prompts: { messageId: number; content: string }[];
  column: number;
  firstRow: number;
  lastRow: number;
}

/** Column order: left, right, then further out on alternating sides (as in a hand sketch). */
function columnCandidates(): number[] {
  const out = [-1, 1];
  for (let k = 2; k <= 50; k++) out.push(k, -k);
  return out;
}

/** Lays out the whole conversation. Empty conversation: no nodes. */
export function layoutConversationMap(state: ConversationState): MapLayout {
  // 1. The trunk: prompts and merge nodes of main. A branch hangs from the prompt
  //    whose answer it is anchored to.
  const mainNodes: MainNode[] = [];
  const anchorOf = new Map<number, number>(); // assistant message id -> main node index
  for (const m of state.main) {
    if (m.role === "user") mainNodes.push({ kind: "prompt", messageId: m.id, content: m.content });
    else if (m.role === "merge") mainNodes.push({ kind: "merge", messageId: m.id, content: "" });
    else if (mainNodes.length > 0) anchorOf.set(m.id, mainNodes.length - 1);
  }
  const mergeIndex = new Map(mainNodes.map((n, i) => [n.messageId, i]));

  const plans: BranchPlan[] = [];
  for (const b of state.branches) {
    const anchor = anchorOf.get(b.anchor_message_id);
    if (anchor === undefined) continue;
    plans.push({
      id: b.id,
      lane: laneOf(state.branches, b.id),
      status: b.status,
      quote: truncate(plainQuote(b.anchor_quote), 90),
      anchor,
      merge: b.merge_message_id === null ? null : (mergeIndex.get(b.merge_message_id) ?? null),
      prompts: b.messages
        .filter((m) => m.role === "user")
        .map((m) => ({ messageId: m.id, content: m.content })),
      column: 0,
      firstRow: 0,
      lastRow: 0,
    });
  }

  // 2. Rows of main. A merged branch needs room for its nodes between its anchor and its
  //    merge node: when there is not enough, the trunk is stretched below the anchor.
  const gap = mainNodes.map(() => 0);
  const rows = (): number[] => {
    const r: number[] = [];
    let row = 0;
    for (let i = 0; i < mainNodes.length; i++) {
      r.push(row);
      row += 1 + gap[i];
    }
    return r;
  };
  for (const p of [...plans].sort((a, b) => a.anchor - b.anchor)) {
    if (p.merge === null) continue;
    const r = rows();
    const needed = Math.max(p.prompts.length, 1);
    const available = r[p.merge] - r[p.anchor] - 1;
    if (available < needed) gap[p.anchor] += needed - available;
  }
  const mainRow = rows();

  // 3. Columns: each branch takes the first column free for the rows it spans.
  const taken = new Map<number, [number, number][]>();
  for (const p of plans) {
    p.firstRow = mainRow[p.anchor] + 1;
    p.lastRow = p.firstRow + Math.max(p.prompts.length, 1) - 1;
    const start = mainRow[p.anchor];
    const end = p.merge === null ? p.lastRow : mainRow[p.merge];
    for (const col of columnCandidates()) {
      const spans = taken.get(col) ?? [];
      if (spans.every(([s, e]) => end < s || start > e)) {
        spans.push([start, end]);
        taken.set(col, spans);
        p.column = col;
        break;
      }
    }
  }

  // 4. Coordinates.
  const columns = [0, ...plans.map((p) => p.column)];
  const minCol = Math.min(...columns);
  const maxCol = Math.max(...columns);
  const x = (col: number): number => PAD + (col - minCol) * COL_W;
  const y = (row: number): number => PAD + row * ROW_H;
  const lastRow = Math.max(0, ...mainRow, ...plans.map((p) => p.lastRow));

  const nodes: MapNode[] = [];
  const edges: MapEdge[] = [];
  const branchLabels: MapBranchLabel[] = [];

  if (mainNodes.length > 0) {
    const x0 = x(0);
    edges.push({
      key: "trunk",
      d: `M ${x0} ${y(mainRow[0])} V ${y(mainRow[mainRow.length - 1])}`,
      lane: null,
      status: null,
    });
    mainNodes.forEach((n, i) => {
      nodes.push({
        key: `main-${n.messageId}`,
        kind: n.kind,
        x: x0,
        y: y(mainRow[i]),
        label: n.kind === "merge" ? "Merge" : nodeText(n.content),
        full: n.kind === "merge" ? "Merge node" : n.content,
        messageId: n.messageId,
        branchId: null,
        lane: null,
        status: null,
      });
    });
  }

  for (const p of plans) {
    const x0 = x(0);
    const xb = x(p.column);
    const ya = y(mainRow[p.anchor]);
    const y1 = y(p.firstRow);
    const yl = y(p.lastRow);
    const bend = (y1 - ya) * 0.6;
    let d = `M ${x0} ${ya} C ${x0} ${ya + bend}, ${xb} ${y1 - bend}, ${xb} ${y1}`;
    if (yl > y1) d += ` V ${yl}`;
    if (p.merge !== null) {
      const ym = y(mainRow[p.merge]);
      const back = (ym - yl) * 0.6;
      d += ` C ${xb} ${yl + back}, ${x0} ${ym - back}, ${x0} ${ym}`;
    }
    edges.push({ key: `branch-${p.id}`, d, lane: p.lane, status: p.status });

    branchLabels.push({
      branchId: p.id,
      lane: p.lane,
      status: p.status,
      quote: p.quote,
      // the curve is a symmetric cubic: its middle is the middle of its ends
      x: (x0 + xb) / 2,
      y: (ya + y1) / 2,
    });

    if (p.prompts.length === 0) {
      nodes.push({
        key: `empty-${p.id}`,
        kind: "empty",
        x: xb,
        y: y1,
        label: "No messages yet",
        full: `Branch on «${p.quote}», no messages yet`,
        messageId: null,
        branchId: p.id,
        lane: p.lane,
        status: p.status,
      });
    }
    p.prompts.forEach((m, i) => {
      nodes.push({
        key: `branch-${p.id}-${m.messageId}`,
        kind: "prompt",
        x: xb,
        y: y(p.firstRow + i),
        label: nodeText(m.content),
        full: m.content,
        messageId: m.messageId,
        branchId: p.id,
        lane: p.lane,
        status: p.status,
      });
    });
  }

  return {
    width: PAD * 2 + (maxCol - minCol) * COL_W,
    height: PAD * 2 + lastRow * ROW_H,
    nodes,
    edges,
    branchLabels,
  };
}
