import { laneOf, plainQuote } from "../lanes";
import type { ConversationState } from "../types";
import { describe, formatCost, formatTokens, useUsage, type UsageTotals } from "../usage";
import { truncate } from "../util";

/** Under an answer: what the call that produced it sent and cost. Nothing when hidden. */
export function AnswerUsageLine({ messageId }: { messageId: number }) {
  const usage = useUsage();
  const found = usage?.messages.find((m) => m.message_id === messageId);
  if (!found) return null;
  return (
    <p className="usage-line" title={`Model: ${found.model}\nTokens in: the whole context sent for this answer.`}>
      {describe(found)}
    </p>
  );
}

function Row({ label, totals, lane }: { label: string; totals: UsageTotals; lane?: number }) {
  return (
    <tr data-lane={lane}>
      <th scope="row">
        {lane !== undefined && <span className="usage-swatch" aria-hidden="true" />}
        {label}
      </th>
      <td>{totals.calls}</td>
      <td>{formatTokens(totals.input_tokens)}</td>
      <td>{formatTokens(totals.output_tokens)}</td>
      <td>{formatCost(totals.cost)}</td>
    </tr>
  );
}

/** In the chat header: the conversation's totals, opening to a breakdown. */
export function ChatUsage({ state }: { state: ConversationState | null }) {
  const usage = useUsage();
  if (!usage || !state || usage.total.calls === 0) return null;
  const { total } = usage;
  return (
    <details className="usage-summary">
      <summary>
        {formatTokens(total.input_tokens + total.output_tokens)} tokens, {formatCost(total.cost)}
      </summary>
      <div className="usage-pop">
        <table className="usage-table">
          <caption>Model calls in this chat</caption>
          <thead>
            <tr>
              <td />
              <th scope="col">Calls</th>
              <th scope="col">In</th>
              <th scope="col">Out</th>
              <th scope="col">Cost</th>
            </tr>
          </thead>
          <tbody>
            <Row label="Answers" totals={usage.chat} />
            <Row label="Take-aways" totals={usage.takeaway} />
            <Row label="Total" totals={total} />
          </tbody>
          <tbody className="usage-threads">
            {usage.threads.map((t) => {
              const branch = state.branches.find((b) => b.id === t.branch_id);
              return (
                <Row
                  key={t.branch_id ?? "main"}
                  label={branch ? `«${truncate(plainQuote(branch.anchor_quote), 28)}»` : "Main"}
                  lane={branch ? laneOf(state.branches, branch.id) : undefined}
                  totals={t}
                />
              );
            })}
          </tbody>
        </table>
        <p className="usage-note">
          “In” counts the whole context sent with each call, so it grows as the chat grows. A
          branch includes its take-away.
        </p>
      </div>
    </details>
  );
}

/** In the branch panel: what this branch has cost so far. */
export function BranchUsage({ branchId }: { branchId: number }) {
  const usage = useUsage();
  const t = usage?.threads.find((x) => x.branch_id === branchId);
  if (!t) return null;
  return (
    <p className="usage-line usage-branch">
      This branch: {t.calls} call{t.calls === 1 ? "" : "s"}, {describe(t)}
    </p>
  );
}
