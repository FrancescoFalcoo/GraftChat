import { branchProps, plainQuote } from "../lanes";
import type { Branch } from "../types";
import { truncate } from "../util";
import { ForkIcon } from "./Marks";

interface Props {
  /** Branches anchored to one assistant message. */
  branches: Branch[];
  activeBranchId: number | null;
  /** Colour of a branch (lanes.ts). */
  colorOf: (branchId: number) => string;
  /** Number of a branch in its conversation (1 = oldest), shown in the chip. */
  numberOf: (branchId: number) => number;
  /** Branches opened a moment ago: their chip pops in. */
  fresh: ReadonlySet<number>;
  onOpenBranch: (branchId: number) => void;
}

const STATUS_WORD: Record<Branch["status"], string> = {
  open: "Open",
  merged: "Merged",
  discarded: "Discarded",
};

/**
 * The branches anchored to a message, each a lane leaving the trunk (highlights are not
 * clickable, these are).
 */
export function AnchorChips({ branches, activeBranchId, colorOf, numberOf, fresh, onOpenBranch }: Props) {
  if (branches.length === 0) return null;
  return (
    <ul className="chips" aria-label="Branches on this answer">
      {branches.map((b) => (
        <li key={b.id} className="chip-row" data-status={b.status} style={branchProps(colorOf(b.id), b.id).style}>
          <button
            type="button"
            className={`chip chip-${b.status}${b.id === activeBranchId ? " chip-active" : ""}`}
            data-branch={b.id}
            data-fresh={fresh.has(b.id) ? "" : undefined}
            aria-pressed={b.id === activeBranchId}
            title={b.anchor_quote}
            onClick={() => onOpenBranch(b.id)}
          >
            <span className="chip-num" aria-hidden="true">
              {numberOf(b.id)}
            </span>
            <ForkIcon />
            <span className="chip-quote">«{truncate(plainQuote(b.anchor_quote), 48)}»</span>
            <span className={`status status-${b.status}`}>{STATUS_WORD[b.status]}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
