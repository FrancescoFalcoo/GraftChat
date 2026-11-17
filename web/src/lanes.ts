import type { Branch } from "./types";

/** Number of lane colours ("tapes"); see --lane-0 … --lane-5 in styles/tokens.css. */
export const LANE_COUNT = 6;

/**
 * Lane of a branch: its position in `branches` (creation order) modulo the number of
 * lanes. The same colour identifies the branch everywhere in the interface.
 */
export function laneOf(branches: Branch[], branchId: number): number {
  const index = branches.findIndex((b) => b.id === branchId);
  return index < 0 ? 0 : index % LANE_COUNT;
}

/** A quoted passage for display only: markdown markers (`*`, `_`, backticks) removed. */
export function plainQuote(quote: string): string {
  return quote.replace(/[*_`]/g, "");
}
