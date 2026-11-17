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

/** Where lanes come back into the trunk: what each merged branch brought back. */
export function MergeNode({ branches, laneOf, fresh, onOpenBranch }: Props) {
  const anyFresh = branches.some((b) => fresh?.has(b.id));
  return (
    <section className="merge-node" aria-label="Merged branches" data-fresh={anyFresh ? "" : undefined}>
      <p className="merge-node-title">Merged {plural(branches.length, "branch")}</p>
      {branches.map((branch) => {
        const included = branch.points.filter((p) => p.included);
        return (
          <div
            key={branch.id}
            className="merge-node-branch"
            data-lane={laneOf(branch.id)}
            data-status="merged"
          >
            <button
              type="button"
              className="quote-link"
              title="Open this branch"
              onClick={() => onOpenBranch(branch.id)}
            >
              «{truncate(plainQuote(branch.anchor_quote), 80)}»
            </button>
            {included.length === 0 ? (
              <p className="merge-node-none">Nothing was brought back from this branch.</p>
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
          </div>
        );
      })}
    </section>
  );
}
