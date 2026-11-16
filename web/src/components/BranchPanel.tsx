import { useEffect, useRef } from "react";
import type { PendingRequest } from "../hooks/useGraft";
import type { Branch } from "../types";
import { Composer } from "./Composer";
import { isAwaitingReply, ThreadView } from "./ThreadView";

interface Props {
  branch: Branch;
  pending: PendingRequest | null;
  onClose: () => void;
  onSend: (text: string) => Promise<boolean>;
  onRetry: () => void;
  onDelete: (messageId: number) => void;
  onMerge: () => void;
  onDiscard: () => void;
}

export function BranchPanel({
  branch,
  pending,
  onClose,
  onSend,
  onRetry,
  onDelete,
  onMerge,
  onDiscard,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isOpen = branch.status === "open";
  const empty = branch.messages.length === 0;
  const awaiting = !pending && isAwaitingReply(branch.messages);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [branch.id, branch.messages.length, pending]);

  const discard = (): void => {
    const question = empty
      ? "Discard this branch?"
      : "Discard this branch? Its messages will never enter the main conversation.";
    if (window.confirm(question)) onDiscard();
  };

  return (
    <aside className="panel" aria-label="Branch">
      <header className="panel-head">
        <div className="panel-title">
          <h2>
            <span aria-hidden="true">⑂</span> Branch
          </h2>
          <span className={`pill pill-${branch.status}`}>{branch.status}</span>
          <button type="button" className="btn btn-small panel-close" onClick={onClose}>
            Close
          </button>
        </div>
        <blockquote className="panel-quote">{branch.anchor_quote}</blockquote>
        {isOpen && (
          <div className="panel-actions">
            <button
              type="button"
              className="btn btn-small btn-primary"
              disabled={empty}
              title={empty ? "Nothing to merge yet: chat in this branch first" : undefined}
              onClick={onMerge}
            >
              Merge…
            </button>
            <button type="button" className="btn btn-small btn-danger" onClick={discard}>
              Discard
            </button>
          </div>
        )}
      </header>

      <div className="panel-scroll" ref={scrollRef}>
        <ThreadView
          messages={branch.messages}
          pending={pending}
          selectable={false}
          canRecover={isOpen}
          onRetry={onRetry}
          onDelete={onDelete}
          emptyHint={
            <p className="muted">
              {isOpen
                ? "Ask about the quoted passage. This side conversation stays out of the main context until you merge it."
                : "This branch has no messages."}
            </p>
          }
        />
      </div>

      <div className="panel-foot">
        {isOpen ? (
          <Composer
            key={branch.id}
            label="Message in this branch"
            placeholder={
              pending
                ? "Waiting for the reply…"
                : awaiting
                  ? "Retry or delete the last message to continue"
                  : "Ask about this passage"
            }
            disabled={pending !== null || awaiting}
            onSend={onSend}
          />
        ) : (
          <p className="panel-closed-note">
            {branch.status === "merged" ? "This branch was merged." : "This branch was discarded."}
          </p>
        )}
      </div>
    </aside>
  );
}
