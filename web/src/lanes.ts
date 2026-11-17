import type { CSSProperties } from "react";
import type { Branch } from "./types";

/**
 * Branch colours, handed out in creation order inside the conversation: the first
 * branch takes POOL[0], the second POOL[1], and so on. A new branch takes the next free
 * colour and existing ones never change. No yellows (the UI accent) and no light blues.
 * Reference implementation: devtools/live.html (generatedColor / branchColor /
 * assignBranchColors).
 */
export const POOL = ["#FF6FAE", "#4ADE9C", "#FF9F5A", "#A78BFA", "#2DD4BF", "#D9A273"] as const;

const GOLDEN_ANGLE = 137.508;
const YELLOW_HUES: [number, number] = [40, 80];

/** Beyond the pool: hues spread by the golden angle, skipping the yellow band. */
export function generatedColor(n: number): string {
  let hue = (n * GOLDEN_ANGLE) % 360;
  if (hue >= YELLOW_HUES[0] && hue <= YELLOW_HUES[1]) hue = (hue + GOLDEN_ANGLE) % 360;
  return `hsl(${hue.toFixed(0)} 72% 68%)`;
}

/** The branches in creation order: created_at, then id. */
export function creationOrder(branches: Branch[]): Branch[] {
  return [...branches].sort(
    (a, b) => String(a.created_at).localeCompare(String(b.created_at)) || a.id - b.id,
  );
}

/** Colour of every branch of a conversation, by branch id. */
export function branchColors(branches: Branch[]): Map<number, string> {
  const colors = new Map<number, string>();
  creationOrder(branches).forEach((b, n) => {
    colors.set(b.id, n < POOL.length ? POOL[n] : generatedColor(n));
  });
  return colors;
}

/** Colour of one branch; an unknown id gets the first pool colour. */
export function branchColor(branches: Branch[], branchId: number): string {
  return branchColors(branches).get(branchId) ?? POOL[0];
}

/** Number of a branch inside its conversation (1 = the oldest), shown in its chip. */
export function branchNumber(branches: Branch[], branchId: number): number {
  return creationOrder(branches).findIndex((b) => b.id === branchId) + 1;
}

/** Props that tie an element to a branch: its colour as --c, its id as data-branch. */
export function branchProps(
  color: string,
  branchId: number,
): { style: CSSProperties; "data-branch": number } {
  return { style: { "--c": color } as CSSProperties, "data-branch": branchId };
}

/** A quoted passage for display only: markdown markers (`*`, `_`, backticks) removed. */
export function plainQuote(quote: string): string {
  return quote.replace(/[*_`]/g, "");
}
