import { useState } from "react";
import { plainQuote } from "../lanes";
import type { Branch } from "../types";
import { plural, truncate } from "../util";

interface Props {
  /** Branches whose merge_message_id is this merge node. */
  branches: Branch[];
  /** Lane colour of a branch (lanes.ts). */
  laneOf: (branchId: number) => number;
  /** Branches merged a moment ago: the node ripples once. */
  fresh?: ReadonlySet<number>;
  onOpenBranch: (branchId: number) => void;
}

/** One merged branch: its passage and how many points it brought back; the points on a click. */
function MergedBranch({ branch, lane, onOpenBranch }: { branch: Branch; lane: number; onOpenBranch: () => void }) {
  const [open, setOpen] = useState(false);
  const included = branch.points.filter((p) => p.included);
  return (
    <div className="merge-node-branch" data-lane={lane} data-status="merged" data-open={open ? "" : undefined}>
      <button type="button" className="merge-node-head" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="merge-node-quote">«{truncate(plainQuote(branch.anchor_quote), 80)}»</span>
        <span className="merge-node-meta">
          {included.length === 0 ? "nothing brought back" : `${included.length} point${included.length === 1 ? "" : "s"} brought back`}
        </span>
        <svg className="merge-node-chevron" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>
      {open && (
        <div className="merge-node-body">
          {included.length === 0 ? (
            <p className="merge-node-none">No point was ticked: nothing from this branch entered the context.</p>
          ) : (
            <ul className="merge-node-points">
              {included.map((p) => (
                <li key={p.id}>
                  <details>
                    <summary>{p.title}</summary>
                    <p>{p.text_final}</p>
                  </details>
                </li>
              ))}
            </ul>
          )}
          <button type="button" className="link-btn merge-node-open" onClick={onOpenBranch}>
            Open this branch
          </button>
        </div>
      )}
    </div>
  );
}

/** Where lanes come back into the trunk: what each merged branch brought back, folded until clicked. */
export function MergeNode({ branches, laneOf, fresh, onOpenBranch }: Props) {
  const anyFresh = branches.some((b) => fresh?.has(b.id));
  return (
    <section className="merge-node" aria-label="Merged branches" data-fresh={anyFresh ? "" : undefined}>
      <p className="merge-node-title">Merged {plural(branches.length, "branch")}</p>
      {branches.map((branch) => (
        <MergedBranch
          key={branch.id}
          branch={branch}
          lane={laneOf(branch.id)}
          onOpenBranch={() => onOpenBranch(branch.id)}
        />
      ))}
    </section>
  );
}
