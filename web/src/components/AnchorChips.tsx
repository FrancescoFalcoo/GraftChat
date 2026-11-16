import type { Branch } from "../types";
import { truncate } from "../util";

interface Props {
  /** Branches anchored to one assistant message. */
  branches: Branch[];
  activeBranchId: number | null;
  onOpenBranch: (branchId: number) => void;
}

/** Clickable list of the branches anchored to a message (highlights are not clickable). */
export function AnchorChips({ branches, activeBranchId, onOpenBranch }: Props) {
  if (branches.length === 0) return null;
  return (
    <div className="chips" aria-label="Branches on this answer">
      {branches.map((b) => (
        <button
          key={b.id}
          type="button"
          className={`chip chip-${b.status}${b.id === activeBranchId ? " chip-active" : ""}`}
          aria-pressed={b.id === activeBranchId}
          title={b.anchor_quote}
          onClick={() => onOpenBranch(b.id)}
        >
          <span aria-hidden="true">⑂</span>
          <span className="chip-quote">«{truncate(b.anchor_quote, 40)}»</span>
          <span className="chip-status">{b.status}</span>
        </button>
      ))}
    </div>
  );
}
