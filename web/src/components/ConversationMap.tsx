import { buildConversationMap, type MapBranch, type MapPrompt } from "../conversationMap";
import type { ConversationState } from "../types";
import { ForkIcon } from "./Marks";
import { Modal } from "./Modal";

interface Props {
  state: ConversationState;
  /** Go to a prompt: `branchId` null = a prompt on main. */
  onJump: (messageId: number, branchId: number | null) => void;
  /** Open a branch in the side panel. */
  onOpenBranch: (branchId: number) => void;
  onClose: () => void;
}

const STATUS_WORD: Record<MapBranch["status"], string> = {
  open: "Open",
  merged: "Merged",
  discarded: "Discarded",
};

function PromptNode({
  prompt,
  branchId,
  onJump,
}: {
  prompt: MapPrompt;
  branchId: number | null;
  onJump: Props["onJump"];
}) {
  return (
    <button
      type="button"
      className="map-node"
      title={prompt.full}
      aria-label={`Go to: ${prompt.full}`}
      onClick={() => onJump(prompt.messageId, branchId)}
    >
      <span className="map-dot" aria-hidden="true" />
      <span className="map-label">{prompt.label}</span>
    </button>
  );
}

function BranchGroup({
  branch,
  onJump,
  onOpenBranch,
}: {
  branch: MapBranch;
  onJump: Props["onJump"];
  onOpenBranch: Props["onOpenBranch"];
}) {
  return (
    <li className="map-branch" data-lane={branch.lane} data-status={branch.status}>
      <button
        type="button"
        className="map-branch-head"
        aria-label={`Open the branch on «${branch.quote}» (${STATUS_WORD[branch.status]})`}
        onClick={() => onOpenBranch(branch.id)}
      >
        <ForkIcon />
        <span className="map-quote">«{branch.quote}»</span>
        <span className="map-status">{STATUS_WORD[branch.status]}</span>
      </button>
      {branch.prompts.length > 0 ? (
        <ul className="map-lane">
          {branch.prompts.map((p) => (
            <li key={p.messageId}>
              <PromptNode prompt={p} branchId={branch.id} onJump={onJump} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="map-empty-branch">No messages yet</p>
      )}
    </li>
  );
}

/** The whole tree of the current conversation, as a dialog. */
export function ConversationMap({ state, onJump, onOpenBranch, onClose }: Props) {
  const rows = buildConversationMap(state);

  return (
    <Modal title="Conversation map" onClose={onClose} wide>
      {rows.length === 0 ? (
        <p className="muted">Nothing here yet. Ask something first.</p>
      ) : (
        <ol className="map" aria-label={`Map of ${state.conversation.title}`}>
          {rows.map((row) =>
            row.kind === "prompt" ? (
              <li key={row.prompt.messageId} className="map-row">
                <PromptNode prompt={row.prompt} branchId={null} onJump={onJump} />
                {row.branches.length > 0 && (
                  <ul className="map-branches">
                    {row.branches.map((b) => (
                      <BranchGroup key={b.id} branch={b} onJump={onJump} onOpenBranch={onOpenBranch} />
                    ))}
                  </ul>
                )}
              </li>
            ) : (
              <li key={row.messageId} className="map-row map-merge">
                <button
                  type="button"
                  className="map-node"
                  aria-label="Go to this merge"
                  onClick={() => onJump(row.messageId, null)}
                >
                  <span className="map-ring" aria-hidden="true" />
                  <span className="map-label">
                    Merged{" "}
                    {row.merged.map((b, i) => (
                      <span key={b.id} className="map-merged" data-lane={b.lane}>
                        {i > 0 ? ", " : ""}«{b.quote}»
                      </span>
                    ))}
                  </span>
                </button>
              </li>
            ),
          )}
        </ol>
      )}
    </Modal>
  );
}
