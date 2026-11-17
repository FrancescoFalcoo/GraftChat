import type { ReactNode } from "react";
import type { MapNode } from "../conversationMap";
import { laneOf, plainQuote } from "../lanes";
import type { Branch, ConversationState, Message } from "../types";
import { truncate } from "../util";

interface Props {
  node: MapNode;
  state: ConversationState;
  onVisit: (node: MapNode) => void;
  onOpenBranch: (branchId: number) => void;
  onClose: () => void;
}

const STATUS: Record<Branch["status"], string> = { open: "open", merged: "merged", discarded: "discarded" };

/** The answer that follows a prompt in its thread, if any. */
function answerTo(thread: Message[], promptId: number): Message | null {
  const i = thread.findIndex((m) => m.id === promptId);
  const next = i >= 0 ? thread[i + 1] : undefined;
  return next && next.role === "assistant" ? next : null;
}

/** Markdown markers out, so an excerpt reads as plain text. */
function plain(text: string): string {
  return text.replace(/[*_`#>]+/g, "").replace(/\n{3,}/g, "\n\n").trim();
}

function BranchChip({ branch, state, onOpen }: { branch: Branch; state: ConversationState; onOpen: () => void }) {
  return (
    <li data-lane={laneOf(state.branches, branch.id)}>
      <button type="button" className="node-branch-chip" onClick={onOpen}>
        <span className="node-branch-quote">«{truncate(plainQuote(branch.anchor_quote), 70)}»</span>
        <span className="node-branch-status">{STATUS[branch.status]}</span>
      </button>
    </li>
  );
}

/** What a block of the map stands for, and the way to go there: shown once it is clicked. */
export function NodeDetails({ node, state, onVisit, onOpenBranch, onClose }: Props) {
  const branch = node.branchId === null ? null : (state.branches.find((b) => b.id === node.branchId) ?? null);
  const thread = branch ? branch.messages : state.main;

  let where: string;
  let body: ReactNode = null;
  let visitLabel: string | null = "Go to this prompt";
  let children: Branch[] = [];

  if (node.kind === "merge") {
    const merged = state.branches.filter((b) => b.merge_message_id === node.messageId);
    const number = state.main.filter((m) => m.role === "merge").findIndex((m) => m.id === node.messageId) + 1;
    where = `Merge ${number} on main`;
    visitLabel = "Go to this merge";
    body = (
      <>
        <p className="node-note">
          {merged.length === 1 ? "One branch came back here." : `${merged.length} branches came back here.`}
        </p>
        <ul className="node-branches">
          {merged.map((b) => (
            <BranchChip key={b.id} branch={b} state={state} onOpen={() => onOpenBranch(b.id)} />
          ))}
        </ul>
      </>
    );
  } else if (node.kind === "empty") {
    where = branch ? `Branch, ${STATUS[branch.status]}` : "Branch";
    visitLabel = null;
    body = (
      <>
        <blockquote className="node-quote">«{node.quote}»</blockquote>
        <p className="node-note">No messages yet.</p>
      </>
    );
  } else {
    const answer = node.messageId === null ? null : answerTo(thread, node.messageId);
    where = branch ? `In the branch on «${truncate(plainQuote(branch.anchor_quote), 60)}», ${STATUS[branch.status]}` : "On main";
    if (!branch && answer) children = state.branches.filter((b) => b.anchor_message_id === answer.id);
    body = (
      <>
        <p className="node-prompt">{node.full}</p>
        {answer ? (
          <>
            <h4 className="node-sub">Answer</h4>
            <p className="node-answer">{truncate(plain(answer.content), 420)}</p>
          </>
        ) : (
          <p className="node-note">No answer yet.</p>
        )}
        {children.length > 0 && (
          <>
            <h4 className="node-sub">Branches from this answer</h4>
            <ul className="node-branches">
              {children.map((b) => (
                <BranchChip key={b.id} branch={b} state={state} onOpen={() => onOpenBranch(b.id)} />
              ))}
            </ul>
          </>
        )}
      </>
    );
  }

  return (
    <section className="node-details" aria-label="Selected block" data-lane={node.lane ?? undefined}>
      <header className="node-head">
        <p className="node-where">{where}</p>
        <button type="button" className="icon-btn" aria-label="Close the details" onClick={onClose}>
          ×
        </button>
      </header>
      <div className="node-body">{body}</div>
      <div className="node-actions">
        {visitLabel && (
          <button type="button" className="btn btn-primary btn-small" onClick={() => onVisit(node)}>
            {visitLabel}
          </button>
        )}
        {branch && (
          <button type="button" className="btn btn-small" onClick={() => onOpenBranch(branch.id)}>
            Open branch
          </button>
        )}
      </div>
    </section>
  );
}
