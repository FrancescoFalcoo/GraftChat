import { branchProps, plainQuote } from "../lanes";
import type { Branch } from "../types";
import { plural, truncate } from "../util";

interface Props {
  /** Branches whose merge_message_id is this merge node. */
  branches: Branch[];
  /** Colour of a branch (lanes.ts). */
  colorOf: (branchId: number) => string;
  /** Number of a branch in its conversation (1 = oldest). */
  numberOf: (branchId: number) => number;
  /** Branches merged a moment ago: the node rings once and their chips pop in. */
  fresh: ReadonlySet<number>;
  onOpenBranch: (branchId: number) => void;
}

/** Where lanes come back into the trunk: what each merged branch brought back. */
export function MergeNode({ branches, colorOf, numberOf, fresh, onOpenBranch }: Props) {
  const anyFresh = branches.some((b) => fresh.has(b.id));
  return (
    <section className="merge-node" aria-label="Merged branches" data-fresh={anyFresh ? "" : undefined}>
      <div className="merge-node-rule">
        <p className="merge-node-title">
          Merged {plural(branches.length, "branch")}
        </p>
        {branches.map((b) => (
          <span
            key={b.id}
            className="merge-chip"
            {...branchProps(colorOf(b.id), b.id)}
            data-fresh={fresh.has(b.id) ? "" : undefined}
            aria-hidden="true"
          >
            <span className="swatch" />
            {numberOf(b.id)}
          </span>
        ))}
      </div>
      {branches.map((branch) => {
        const included = branch.points.filter((p) => p.included);
        return (
          <div
            key={branch.id}
            className="merge-node-branch"
            {...branchProps(colorOf(branch.id), branch.id)}
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
