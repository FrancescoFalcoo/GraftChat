import { plainQuote } from "../lanes";
import type { Branch } from "../types";
import { truncate } from "../util";
import { ForkIcon } from "./Marks";

interface Props {
  /** Branches anchored to one assistant message. */
  branches: Branch[];
  activeBranchId: number | null;
  /** Lane colour of a branch (lanes.ts). */
  laneOf: (branchId: number) => number;
  /** Branches opened a moment ago: their chip pops in. */
  fresh?: ReadonlySet<number>;
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
export function AnchorChips({ branches, activeBranchId, laneOf, fresh, onOpenBranch }: Props) {
  if (branches.length === 0) return null;
  return (
    <ul className="chips" aria-label="Branches on this answer">
      {branches.map((b) => (
        <li key={b.id} className="chip-row" data-lane={laneOf(b.id)} data-status={b.status}>
          <button
            type="button"
            className={`chip chip-${b.status}${b.id === activeBranchId ? " chip-active" : ""}`}
            data-fresh={fresh?.has(b.id) ? "" : undefined}
            aria-pressed={b.id === activeBranchId}
            title={b.anchor_quote}
            onClick={() => onOpenBranch(b.id)}
          >
            <ForkIcon />
            <span className="chip-quote">«{truncate(plainQuote(b.anchor_quote), 48)}»</span>
            <span className="chip-status">{STATUS_WORD[b.status]}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
