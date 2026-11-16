import type { ReactNode } from "react";
import type { PendingRequest } from "../hooks/useGraft";
import type { Message } from "../types";
import { MessageContent } from "./MessageContent";

interface Props {
  messages: Message[];
  /** The model call in flight on this thread, if any. */
  pending: PendingRequest | null;
  /** Assistant messages can be selected to open a branch (main only). */
  selectable: boolean;
  /** False when the thread can no longer change (merged or discarded branch). */
  canRecover?: boolean;
  onRetry: () => void;
  onDelete: (messageId: number) => void;
  renderMerge?: (message: Message) => ReactNode;
  /** Extra content under an assistant message (anchor chips). */
  renderBelow?: (message: Message) => ReactNode;
  emptyHint: ReactNode;
}

/** True when the thread ends with a user message nobody answered. */
export function isAwaitingReply(messages: Message[]): boolean {
  return messages.at(-1)?.role === "user";
}

export function ThreadView({
  messages,
  pending,
  selectable,
  canRecover = true,
  onRetry,
  onDelete,
  renderMerge,
  renderBelow,
  emptyHint,
}: Props) {
  const dangling = !pending && canRecover && isAwaitingReply(messages);
  const last = messages.at(-1);

  if (messages.length === 0 && !pending) {
    return <div className="thread-empty">{emptyHint}</div>;
  }

  return (
    <div className="thread">
      {messages.map((m) => {
        if (m.role === "merge") {
          return <div key={m.id}>{renderMerge ? renderMerge(m) : null}</div>;
        }
        if (m.role === "user") {
          return (
            <div key={m.id} className="msg msg-user">
              <div className="bubble">{m.content}</div>
              {dangling && last?.id === m.id && (
                <div className="dangling" role="group" aria-label="No reply was received">
                  <span className="dangling-note">No reply was received.</span>
                  <button type="button" className="btn btn-small btn-primary" onClick={onRetry}>
                    Retry
                  </button>
                  <button type="button" className="btn btn-small" onClick={() => onDelete(m.id)}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          );
        }
        return (
          <div key={m.id} className="msg msg-assistant">
            <MessageContent content={m.content} messageId={m.id} selectable={selectable} />
            {renderBelow ? renderBelow(m) : null}
          </div>
        );
      })}
      {pending && pending.text !== null && (
        <div className="msg msg-user msg-optimistic">
          <div className="bubble">{pending.text}</div>
        </div>
      )}
      {pending && (
        <div className="msg msg-assistant thinking" role="status">
          <span className="spinner" aria-hidden="true" />
          Thinking…
        </div>
      )}
    </div>
  );
}
