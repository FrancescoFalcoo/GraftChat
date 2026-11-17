import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useAnchorClicks } from "../hooks/useAnchorClicks";
import { useAnchorHighlights } from "../hooks/useAnchorHighlights";
import { useFreshIds } from "../hooks/useFreshIds";
import { laneOf } from "../lanes";
import type { PendingRequest } from "../hooks/useGraft";
import type { AnchorSelection } from "../selection";
import type { Branch, ConversationState, Message } from "../types";
import { AnchorChips } from "./AnchorChips";
import { Composer } from "./Composer";
import { GraftDiagram } from "./Marks";
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
  onSend: (text: string, images: File[]) => Promise<boolean>;
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
  const laneOfId = useCallback((id: number) => laneOf(branches, id), [branches]);
  const conversationKey = state?.conversation.id ?? null;
  const freshBranches = useFreshIds(conversationKey, branches.map((b) => b.id));
  // A merge may reuse the last merge node: what is new is the merged branch.
  const freshMerged = useFreshIds(
    conversationKey,
    branches.filter((b) => b.status === "merged").map((b) => b.id),
  );

  const contentOf = useCallback(
    (messageId: number): string | null => {
      const m = state?.main.find((x) => x.id === messageId);
      return m && m.role === "assistant" && m.branch_id === null ? m.content : null;
    },
    [state],
  );

  useAnchorHighlights(scopeRef, state, activeBranchId);
  useAnchorClicks(scopeRef, state, onShowBranch);

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
    <MergeNode branches={byMerge.get(m.id) ?? []} laneOf={laneOfId} fresh={freshMerged} onOpenBranch={onShowBranch} />
  );
  const renderBelow = (m: Message): ReactNode => (
    <AnchorChips
      branches={byAnchor.get(m.id) ?? []}
      activeBranchId={activeBranchId}
      laneOf={laneOfId}
      fresh={freshBranches}
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
            scope={`c${conversationKey ?? ""}`}
            messages={messages}
            pending={pending}
            selectable
            onRetry={onRetry}
            onDelete={onDelete}
            renderMerge={renderMerge}
            renderBelow={renderBelow}
            emptyHint={
              booting ? (
                <p className="muted loading">Loading…</p>
              ) : (
                <div className="first-screen">
                  <GraftDiagram />
                  <p>Ask something, then select any part of the answer to branch from it.</p>
                </div>
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
            Enter to send, Shift+Enter for a new line. Select any part of an answer to branch from it.
          </p>
        </div>
      </div>
      <SelectionPopover scopeRef={scopeRef} contentOf={contentOf} onOpen={onOpenBranch} />
    </main>
  );
}
