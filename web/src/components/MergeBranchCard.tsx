import { plainQuote } from "../lanes";
import type { Branch, ConversationState } from "../types";
import { AddPoint } from "./AddPoint";
import { PointRow } from "./PointRow";

export type Decision = "merge" | "later" | "discard";

export interface TakeawayStatus {
  loading: boolean;
  error: string | null;
}

interface Props {
  branch: Branch;
  /** Lane colour of the branch (lanes.ts). */
  lane?: number;
  decision: Decision;
  takeaway: TakeawayStatus | null;
  /** A take-away is being generated for some branch (they run one at a time). */
  anyGenerating: boolean;
  /** Apply is running: everything is read-only. */
  locked: boolean;
  onDecision: (decision: Decision) => void;
  onRetry: () => void;
  onRegenerate: () => void;
  onState: (state: ConversationState) => void;
  onError: (error: unknown) => void;
  onPointBusy: (pointId: number, busy: boolean) => void;
}

const CHOICES: { value: Decision; label: string }[] = [
  { value: "merge", label: "Merge" },
  { value: "later", label: "Decide later" },
  { value: "discard", label: "Discard" },
];

export function MergeBranchCard({
  branch,
  lane = 0,
  decision,
  takeaway,
  anyGenerating,
  locked,
  onDecision,
  onRetry,
  onRegenerate,
  onState,
  onError,
  onPointBusy,
}: Props) {
  const empty = branch.messages.length === 0;
  const count = branch.messages.length;
  const loading = takeaway?.loading ?? false;
  const included = branch.points.filter((p) => p.included).length;

  return (
    <section
      className={`merge-card merge-card-${decision}`}
      aria-label={`Branch on: ${branch.anchor_quote}`}
      data-lane={lane}
      data-decision={decision}
    >
      <blockquote className="merge-quote">{plainQuote(branch.anchor_quote)}</blockquote>
      <div className="merge-card-row">
        <span className="muted">
          {empty ? "No messages" : `${count} message${count === 1 ? "" : "s"}`}
        </span>
        <fieldset className="segmented" disabled={locked}>
          <legend className="sr-only">Decision for this branch</legend>
          {CHOICES.map((choice) => {
            const disabled = choice.value === "merge" && empty;
            return (
              <label
                key={choice.value}
                className={`segment${decision === choice.value ? " segment-on" : ""}${disabled ? " segment-disabled" : ""}`}
                title={disabled ? "An empty branch cannot be merged" : undefined}
              >
                <input
                  type="radio"
                  name={`decision-${branch.id}`}
                  value={choice.value}
                  checked={decision === choice.value}
                  disabled={disabled}
                  onChange={() => onDecision(choice.value)}
                />
                {choice.label}
              </label>
            );
          })}
        </fieldset>
      </div>

      {decision === "discard" && (
        <p className="merge-card-note">
          This branch will be discarded when you apply. It never enters the main context.
        </p>
      )}

      {decision === "merge" && (
        <div className="takeaway">
          {loading && (
            <p className="takeaway-status" role="status">
              <span className="spinner" aria-hidden="true" />
              Generating take-away…
            </p>
          )}
          {!loading && takeaway?.error && (
            <div className="takeaway-error" role="alert">
              <p>{takeaway.error}</p>
              <button type="button" className="btn btn-small" onClick={onRetry}>
                Retry
              </button>
            </div>
          )}
          {!loading && !takeaway?.error && branch.points.length === 0 && !takeaway && (
            <p className="takeaway-status muted">Waiting to generate the take-away…</p>
          )}
          {!loading && !takeaway?.error && branch.points.length === 0 && takeaway && (
            <div className="takeaway-error">
              <p>The model returned no points for this branch.</p>
              <button
                type="button"
                className="btn btn-small"
                disabled={anyGenerating || locked}
                onClick={onRegenerate}
              >
                Regenerate
              </button>
            </div>
          )}
          {!loading && branch.points.length > 0 && (
            <>
              <div className="takeaway-head">
                <span className="muted">
                  {included} of {branch.points.length} point{branch.points.length === 1 ? "" : "s"}{" "}
                  will enter the main context
                </span>
                <button
                  type="button"
                  className="btn btn-small"
                  disabled={anyGenerating || locked}
                  onClick={onRegenerate}
                >
                  Regenerate
                </button>
              </div>
              <ul className="points">
                {branch.points.map((p) => (
                  <PointRow
                    key={p.id}
                    point={p}
                    disabled={locked}
                    onState={onState}
                    onError={onError}
                    onBusy={onPointBusy}
                  />
                ))}
              </ul>
            </>
          )}
          {!loading && !empty && (takeaway !== null || branch.points.length > 0) && (
            <AddPoint branchId={branch.id} disabled={locked} onState={onState} onError={onError} />
          )}
        </div>
      )}
    </section>
  );
}
