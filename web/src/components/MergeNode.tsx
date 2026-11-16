import type { Branch } from "../types";
import { plural, truncate } from "../util";

interface Props {
  /** Branches whose merge_message_id is this merge node. */
  branches: Branch[];
  onOpenBranch: (branchId: number) => void;
}

/** Divider card shown on main where branches were merged. */
export function MergeNode({ branches, onOpenBranch }: Props) {
  return (
    <section className="merge-node" aria-label="Merged branches">
      <div className="merge-node-title">
        <span aria-hidden="true">⑂</span> Merged {plural(branches.length, "branch")}
      </div>
      {branches.map((branch) => {
        const included = branch.points.filter((p) => p.included);
        return (
          <div key={branch.id} className="merge-node-branch">
            <button
              type="button"
              className="quote-link"
              title="Open this branch"
              onClick={() => onOpenBranch(branch.id)}
            >
              «{truncate(branch.anchor_quote, 80)}»
            </button>
            {included.length === 0 ? (
              <p className="muted">nothing brought back</p>
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
