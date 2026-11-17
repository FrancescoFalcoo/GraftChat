import { useEffect, useRef, useState } from "react";
import type { PendingRequest } from "../hooks/useGraft";
import { plainQuote } from "../lanes";
import type { Branch } from "../types";
import { Composer } from "./Composer";
import { ConfirmDialog } from "./ConfirmDialog";
import { ForkIcon } from "./Marks";
import { isAwaitingReply, ThreadView } from "./ThreadView";

interface Props {
  branch: Branch;
  /** Lane colour of the branch (lanes.ts): the rail down the panel's left edge. */
  lane: number;
  /** Merged branches whose take-aways this branch knows (util.knownMerges). */
  known: Branch[];
  pending: PendingRequest | null;
  onClose: () => void;
  onSend: (text: string, files: File[]) => Promise<boolean>;
  onRetry: () => void;
  onDelete: (messageId: number) => void;
  onMerge: () => void;
  onDiscard: () => void;
}

const STATUS_WORD: Record<Branch["status"], string> = {
  open: "Open",
  merged: "Merged",
  discarded: "Discarded",
};

export function BranchPanel({
  branch,
  lane,
  known,
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

  const [confirming, setConfirming] = useState(false);
  // A new branch: the composer sits right under the hint, where one starts typing.
  const fresh = isOpen && empty && !pending;

  const composer = (
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
  );

  return (
    <aside className="panel" aria-label="Branch" data-lane={lane} data-status={branch.status}>
      <header className="panel-head">
        <div className="panel-title">
          <h2>
            <ForkIcon /> Branch
          </h2>
          <span className={`pill pill-${branch.status}`}>{STATUS_WORD[branch.status]}</span>
          <button type="button" className="btn btn-small panel-close" onClick={onClose}>
            Close
          </button>
        </div>
        <blockquote className="panel-quote" title={branch.anchor_quote}>
          {plainQuote(branch.anchor_quote)}
        </blockquote>
        {known.length > 0 && (
          <p
            className="panel-known"
            title={known.map((b) => `«${plainQuote(b.anchor_quote)}»`).join("\n")}
          >
            Knows the take-aways of {known.length} merged{" "}
            {known.length === 1 ? "branch" : "branches"}
          </p>
        )}
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
            <button type="button" className="btn btn-small btn-danger" onClick={() => setConfirming(true)}>
              Discard
            </button>
          </div>
        )}
      </header>

      <div className="panel-scroll" ref={scrollRef}>
        <ThreadView
          scope={`b${branch.id}`}
          messages={branch.messages}
          pending={pending}
          selectable={false}
          canRecover={isOpen}
          onRetry={onRetry}
          onDelete={onDelete}
          emptyHint={
            <>
              <p className="muted">
                {isOpen
                  ? "Ask about the quoted passage. This side conversation stays out of the main context until you merge it."
                  : "This branch has no messages."}
              </p>
              {fresh && <div className="panel-first-composer">{composer}</div>}
            </>
          }
        />
      </div>

      {!fresh && (
        <div className="panel-foot">
          {isOpen ? (
            composer
          ) : (
            <p className="panel-closed-note">
              {branch.status === "merged" ? "This branch was merged." : "This branch was discarded."}
            </p>
          )}
        </div>
      )}

      {confirming && (
        <ConfirmDialog
          title="Discard this branch?"
          message={
            empty
              ? "The branch will be closed. You can still see it on the map."
              : "Its messages will never enter the main conversation. You can still read them later."
          }
          confirmLabel="Discard"
          danger
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false);
            onDiscard();
          }}
        />
      )}
    </aside>
  );
}
