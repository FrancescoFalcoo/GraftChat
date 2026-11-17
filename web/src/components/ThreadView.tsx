import type { ReactNode } from "react";
import { attachmentUrl } from "../api";
import { useFreshIds } from "../hooks/useFreshIds";
import type { PendingRequest } from "../hooks/useGraft";
import type { Attachment, Message } from "../types";
import { MessageContent } from "./MessageContent";

interface Props {
  /** What this thread belongs to (conversation or branch): answers new within it fade in. */
  scope: string;
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

function Images({ items }: { items: { key: string; src: string; name: string }[] }) {
  if (items.length === 0) return null;
  return (
    <div className="msg-images">
      {items.map((i) => (
        <a key={i.key} href={i.src} target="_blank" rel="noreferrer" title={i.name}>
          <img src={i.src} alt={i.name} loading="lazy" />
        </a>
      ))}
    </div>
  );
}

function stored(attachments: Attachment[] | undefined) {
  return (attachments ?? []).map((a) => ({ key: `a${a.id}`, src: attachmentUrl(a.id), name: a.name }));
}

/** True when the thread ends with a user message nobody answered. */
export function isAwaitingReply(messages: Message[]): boolean {
  return messages.at(-1)?.role === "user";
}

export function ThreadView({
  scope,
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
  const freshAnswers = useFreshIds(
    scope,
    messages.filter((m) => m.role === "assistant").map((m) => m.id),
  );

  if (messages.length === 0 && !pending) {
    return <div className="thread-empty">{emptyHint}</div>;
  }

  return (
    <div className="thread">
      {messages.map((m) => {
        if (m.role === "merge") {
          return (
            <div key={m.id} className="turn turn-merge" data-turn-id={m.id}>
              {renderMerge ? renderMerge(m) : null}
            </div>
          );
        }
        if (m.role === "user") {
          return (
            <div key={m.id} className="turn turn-user msg msg-user" data-turn-id={m.id}>
              <Images items={stored(m.attachments)} />
              {m.content !== "" && <div className="user-text">{m.content}</div>}
              {dangling && last?.id === m.id && (
                <div className="dangling" role="group" aria-label="No reply was received">
                  <span className="dangling-note">No reply was received. Retry, or delete this message.</span>
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
          <div
            key={m.id}
            className="turn turn-assistant msg msg-assistant"
            data-turn-id={m.id}
            data-fresh={freshAnswers.has(m.id) ? "" : undefined}
          >
            <MessageContent content={m.content} messageId={m.id} selectable={selectable} />
            {renderBelow ? renderBelow(m) : null}
          </div>
        );
      })}
      {pending && pending.text !== null && (
        <div className="turn turn-user msg msg-user msg-optimistic">
          <Images
            items={(pending.images ?? []).map((src, i) => ({ key: `p${i}`, src, name: "image" }))}
          />
          {pending.text !== "" && <div className="user-text">{pending.text}</div>}
        </div>
      )}
      {pending && (
        <div className="turn turn-assistant turn-thinking thinking" role="status">
          <span className="spinner" aria-hidden="true" />
          <span className="thinking-text">Thinking…</span>
        </div>
      )}
    </div>
  );
}
