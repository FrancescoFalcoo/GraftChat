/**
 * The logbook: what a conversation established, in the order it happened, for someone
 * coming back to it later. It is built from what the user already chose to keep: the
 * take-away points of merged branches (ticked ones first; the unticked ones stay
 * readable). Summaries of old messages (docs/CONTEXT.md) will join here when they exist.
 */

import { laneOf, plainQuote } from "./lanes";
import type { ConversationState, Point } from "./types";

export interface LogbookBranch {
  id: number;
  lane: number;
  quote: string;
  /** Points that entered the main context, in checklist order. */
  kept: Point[];
  /** Points the user unticked: not in the context, kept for the record. */
  left: Point[];
  prompts: number;
}

export interface LogbookMerge {
  /** The merge node on main. */
  messageId: number;
  /** 1-based count of merges so far, in main order. */
  number: number;
  branches: LogbookBranch[];
}

export interface Logbook {
  /** The first prompt of main: what the conversation set out to do. */
  start: { messageId: number; text: string } | null;
  prompts: number;
  merges: LogbookMerge[];
  open: LogbookBranch[];
  discarded: LogbookBranch[];
}

function entry(state: ConversationState, branchId: number): LogbookBranch {
  const b = state.branches.find((x) => x.id === branchId)!;
  const points = [...b.points].sort((p, q) => p.position - q.position);
  return {
    id: b.id,
    lane: laneOf(state.branches, b.id),
    quote: plainQuote(b.anchor_quote),
    kept: points.filter((p) => p.included),
    left: points.filter((p) => !p.included),
    prompts: b.messages.filter((m) => m.role === "user").length,
  };
}

export function buildLogbook(state: ConversationState): Logbook {
  const first = state.main.find((m) => m.role === "user") ?? null;
  const merges: LogbookMerge[] = [];
  for (const m of state.main) {
    if (m.role !== "merge") continue;
    const branches = state.branches
      .filter((b) => b.status === "merged" && b.merge_message_id === m.id)
      .sort((a, b) => a.id - b.id) // the order the model reads them in (DESIGN §14.10)
      .map((b) => entry(state, b.id));
    if (branches.length > 0) merges.push({ messageId: m.id, number: merges.length + 1, branches });
  }
  return {
    start: first ? { messageId: first.id, text: first.content } : null,
    prompts: state.main.filter((m) => m.role === "user").length,
    merges,
    open: state.branches.filter((b) => b.status === "open").map((b) => entry(state, b.id)),
    discarded: state.branches.filter((b) => b.status === "discarded").map((b) => entry(state, b.id)),
  };
}

/** The logbook in one line, for when it is folded: "2 merges, 11 points". */
export function logbookSummary(log: Logbook): string {
  if (log.merges.length === 0) return "nothing merged yet";
  const kept = log.merges.reduce((n, m) => n + m.branches.reduce((k, b) => k + b.kept.length, 0), 0);
  const merges = `${log.merges.length} merge${log.merges.length === 1 ? "" : "s"}`;
  return `${merges}, ${kept} point${kept === 1 ? "" : "s"}`;
}
