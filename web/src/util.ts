import type { Branch, ConversationState, Message } from "./types";

const LAST_CONVERSATION_KEY = "graftchat.lastConversationId";

export function loadLastConversationId(): number | null {
  try {
    const raw = window.localStorage.getItem(LAST_CONVERSATION_KEY);
    if (raw === null) return null;
    const id = Number(raw);
    return Number.isInteger(id) ? id : null;
  } catch {
    return null;
  }
}

export function saveLastConversationId(id: number | null): void {
  try {
    if (id === null) window.localStorage.removeItem(LAST_CONVERSATION_KEY);
    else window.localStorage.setItem(LAST_CONVERSATION_KEY, String(id));
  } catch {
    // Storage may be unavailable (private mode, quota): the app works without it.
  }
}

/** Shortens to about `max` characters (code points), on one line, with an ellipsis. */
export function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const chars = Array.from(flat);
  return chars.length <= max ? flat : chars.slice(0, max).join("").trimEnd() + "…";
}

export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "es"}`;
}

/** Key of a thread in the "request in flight" map. `branchId` null = main. */
export function threadKey(conversationId: number, branchId: number | null): string {
  return `${conversationId}:${branchId ?? "main"}`;
}

export function threadMessages(state: ConversationState, branchId: number | null): Message[] {
  if (branchId === null) return state.main;
  return state.branches.find((b) => b.id === branchId)?.messages ?? [];
}

/** Branches waiting for a merge decision (falls back to open ones while core is a stub). */
export function pendingBranches(state: ConversationState): Branch[] {
  const ids = state.pending_branch_ids;
  if (ids === null) return state.branches.filter((b) => b.status === "open");
  return state.branches.filter((b) => ids.includes(b.id));
}

export function isEmptyConversation(state: ConversationState): boolean {
  return state.main.length === 0 && state.branches.length === 0;
}

/**
 * The merged branches whose take-away a branch knows (DESIGN.md §14.11): those merged on
 * main up to the branch's base (the end of main when it was opened; its anchor for branches
 * stored before bases existed), with at least one point ticked.
 */
export function knownMerges(state: ConversationState, branch: Branch): Branch[] {
  const position = new Map(state.main.map((m, i) => [m.id, i]));
  const limit = position.get(branch.base_message_id ?? branch.anchor_message_id);
  if (limit === undefined) return [];
  return state.branches.filter((b) => {
    if (b.id === branch.id || b.status !== "merged" || b.merge_message_id === null) return false;
    const at = position.get(b.merge_message_id);
    return at !== undefined && at <= limit && b.points.some((p) => p.included);
  });
}
