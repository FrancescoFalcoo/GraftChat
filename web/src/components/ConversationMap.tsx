import { layoutConversationMap, type MapNode } from "../conversationMap";
import type { CSSProperties } from "react";
import type { BranchStatus, ConversationState } from "../types";
import { Modal } from "./Modal";

interface Props {
  state: ConversationState;
  /** Go to a message: `branchId` null = a message on main. */
  onJump: (messageId: number, branchId: number | null) => void;
  /** Open a branch in the side panel. */
  onOpenBranch: (branchId: number) => void;
  onClose: () => void;
}

const STATUS_WORD: Record<BranchStatus, string> = {
  open: "open",
  merged: "merged",
  discarded: "discarded",
};

/** The branch colour as --c (nothing for main). */
function colorStyle(color: string | null): CSSProperties {
  return color === null ? {} : ({ "--c": color } as CSSProperties);
}

function Node({ node, onJump, onOpenBranch }: { node: MapNode } & Omit<Props, "state" | "onClose">) {
  const click = (): void => {
    if (node.messageId !== null) onJump(node.messageId, node.branchId);
    else if (node.branchId !== null) onOpenBranch(node.branchId);
  };
  return (
    <button
      type="button"
      className={`map-node map-node-${node.kind}`}
      style={{ left: node.x, top: node.y, ...colorStyle(node.color) }}
      data-branch={node.branchId ?? undefined}
      data-status={node.status ?? undefined}
      title={node.full}
      aria-label={node.kind === "merge" ? "Go to this merge" : `Go to: ${node.full}`}
      onClick={click}
    >
      <span className="map-dot" aria-hidden="true" />
      <span className="map-label">{node.label}</span>
    </button>
  );
}

/** The whole tree of the current conversation, drawn as a graph, in a dialog. */
export function ConversationMap({ state, onJump, onOpenBranch, onClose }: Props) {
  const layout = layoutConversationMap(state);

  return (
    <Modal title="Conversation map" onClose={onClose} wide>
      {layout.nodes.length === 0 ? (
        <p className="muted">Nothing here yet. Ask something first.</p>
      ) : (
        <div className="map-scroll">
          <div
            className="map"
            role="group"
            aria-label={`Map of ${state.conversation.title}`}
            style={{ width: layout.width, height: layout.height }}
          >
            <svg className="map-edges" width={layout.width} height={layout.height} aria-hidden="true">
              {layout.edges.map((e) => (
                <path
                  key={e.key}
                  d={e.d}
                  className={e.branchId === null ? "map-trunk" : "map-edge"}
                  style={colorStyle(e.color)}
                  data-branch={e.branchId ?? undefined}
                  data-status={e.status ?? undefined}
                />
              ))}
            </svg>
            {layout.branchLabels.map((b) => (
              <button
                key={`label-${b.branchId}`}
                type="button"
                className="map-branch-label"
                style={{ left: b.x, top: b.y, ...colorStyle(b.color) }}
                data-branch={b.branchId}
                data-status={b.status}
                aria-label={`Open the branch on «${b.quote}» (${STATUS_WORD[b.status]})`}
                onClick={() => onOpenBranch(b.branchId)}
              >
                «{b.quote}» <span className="map-status">{STATUS_WORD[b.status]}</span>
              </button>
            ))}
            {layout.nodes.map((n) => (
              <Node key={n.key} node={n} onJump={onJump} onOpenBranch={onOpenBranch} />
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}
