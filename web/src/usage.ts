import { createContext, useContext } from "react";

/** Tokens and cost of some model calls (docs/API.md, "usage"). */
export interface UsageTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

/** What one answer cost: `input_tokens` is the whole context the model received for it. */
export interface AnswerUsage {
  message_id: number;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

export interface Usage {
  total: UsageTotals;
  chat: UsageTotals;
  takeaway: UsageTotals;
  /** Per thread: `branch_id` null = main; a take-away counts for its branch. */
  threads: (UsageTotals & { branch_id: number | null })[];
  messages: AnswerUsage[];
}

/** Where the "show tokens and cost" choice is remembered (Settings). */
export const SHOW_USAGE_KEY = "graftchat.showUsage";

/** The usage of the open conversation, or null when the figures are hidden. */
export const UsageContext = createContext<Usage | null>(null);

export function useUsage(): Usage | null {
  return useContext(UsageContext);
}

export function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatCost(usd: number): string {
  if (usd === 0) return "free";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** "1,240 tokens in, 312 out, $0.0012". */
export function describe(t: { input_tokens: number; output_tokens: number; cost: number }): string {
  return `${formatTokens(t.input_tokens)} tokens in, ${formatTokens(t.output_tokens)} out, ${formatCost(t.cost)}`;
}
