import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useAnchorHighlights } from "../hooks/useAnchorHighlights";
import type { PendingRequest } from "../hooks/useGraft";
import type { AnchorSelection } from "../selection";
import type { Branch, ConversationState, Message } from "../types";
import { AnchorChips } from "./AnchorChips";
import { Composer } from "./Composer";
import { MergeNode } from "./MergeNode";
import { SelectionPopover } from "./SelectionPopover";
import { isAwaitingReply, ThreadView } from "./ThreadView";

interface Props {
  state: ConversationState | null;
  booting: boolean;
  pending: PendingRequest | null;
  activeBranchId: number | null;
  /** Rendered above the composer (return-to-main banner). */
  banner: ReactNode;
  onSend: (text: string) => Promise<boolean>;
  onRetry: () => void;
  onDelete: (messageId: number) => void;
  onOpenBranch: (messageId: number, selection: AnchorSelection) => Promise<boolean>;
  onShowBranch: (branchId: number) => void;
}

function groupBy(branches: Branch[], key: (b: Branch) => number | null): Map<number, Branch[]> {
  const map = new Map<number, Branch[]>();
  for (const b of branches) {
    const k = key(b);
    if (k === null) continue;
    const list = map.get(k);
    if (list) list.push(b);
    else map.set(k, [b]);
  }
  return map;
}

export function MainChat({
  state,
  booting,
  pending,
  activeBranchId,
  banner,
  onSend,
  onRetry,
  onDelete,
  onOpenBranch,
  onShowBranch,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const scopeRef = useRef<HTMLDivElement>(null);
  const messages = state?.main ?? [];
  const branches = state?.branches ?? [];

  const byAnchor = useMemo(() => groupBy(branches, (b) => b.anchor_message_id), [branches]);
  const byMerge = useMemo(() => groupBy(branches, (b) => b.merge_message_id), [branches]);

  const contentOf = useCallback(
    (messageId: number): string | null => {
      const m = state?.main.find((x) => x.id === messageId);
      return m && m.role === "assistant" && m.branch_id === null ? m.content : null;
    },
    [state],
  );

  useAnchorHighlights(scopeRef, state, activeBranchId);

  // Follow the conversation: scroll to the end when a message or a placeholder is added.
  const conversationId = state?.conversation.id ?? null;
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [conversationId, messages.length, pending]);

  const awaiting = !pending && isAwaitingReply(messages);
  const placeholder = pending
    ? "Waiting for the reply…"
    : awaiting
      ? "Retry or delete the last message to continue"
      : "Message GraftChat";

  const renderMerge = (m: Message): ReactNode => (
    <MergeNode branches={byMerge.get(m.id) ?? []} onOpenBranch={onShowBranch} />
  );
  const renderBelow = (m: Message): ReactNode => (
    <AnchorChips
      branches={byAnchor.get(m.id) ?? []}
      activeBranchId={activeBranchId}
      onOpenBranch={onShowBranch}
    />
  );

  return (
    <main className="chat">
      <header className="chat-head">
        <h1>{state?.conversation.title ?? "GraftChat"}</h1>
      </header>
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-col" ref={scopeRef}>
          <ThreadView
            messages={messages}
            pending={pending}
            selectable
            onRetry={onRetry}
            onDelete={onDelete}
            renderMerge={renderMerge}
            renderBelow={renderBelow}
            emptyHint={
              booting ? (
                <p className="muted">Loading…</p>
              ) : (
                <>
                  <h2>Start a conversation</h2>
                  <p className="muted">
                    Ask something. Then select a passage of an answer to open a branch on it, and
                    merge back only the points you want to keep.
                  </p>
                </>
              )
            }
          />
        </div>
      </div>
      <div className="chat-foot">
        <div className="chat-col">
          {banner}
          <Composer
            label="Message"
            placeholder={placeholder}
            disabled={booting || pending !== null || awaiting}
            onSend={onSend}
          />
          <p className="composer-hint">
            Enter to send, Shift+Enter for a new line. Select text in an answer to open a branch.
          </p>
        </div>
      </div>
      <SelectionPopover scopeRef={scopeRef} contentOf={contentOf} onOpen={onOpenBranch} />
    </main>
  );
}
