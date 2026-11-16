import { useCallback, useEffect, useRef, useState } from "react";
import { api, toApiError } from "../api";
import type { MergeFocus } from "../hooks/useGraft";
import type { Branch, ConversationState } from "../types";
import { MergeBranchCard, type Decision, type TakeawayStatus } from "./MergeBranchCard";
import { Modal } from "./Modal";

interface Props {
  state: ConversationState;
  /** Branches pre-set to "Merge": the one the user clicked, or all (from the banner). */
  focus: MergeFocus;
  /** Every mutating call returns the fresh state: it replaces the whole one. */
  onState: (state: ConversationState) => void;
  onClose: () => void;
  onApplied: () => void;
  onError: (error: unknown) => void;
  /** Called after each take-away call (the month spend may have changed). */
  onModelCall: () => void;
}

function initialDecisions(branches: Branch[], focus: MergeFocus): Record<number, Decision> {
  const decisions: Record<number, Decision> = {};
  for (const b of branches) {
    const targeted = focus === "all" || focus.includes(b.id);
    decisions[b.id] = targeted && b.messages.length > 0 ? "merge" : "later";
  }
  return decisions;
}

export function MergeDialog({
  state,
  focus,
  onState,
  onClose,
  onApplied,
  onError,
  onModelCall,
}: Props) {
  const open = state.branches.filter((b) => b.status === "open");
  const [decisions, setDecisions] = useState(() => initialDecisions(open, focus));
  const [takeaways, setTakeaways] = useState<Record<number, TakeawayStatus>>({});
  const [busyPoints, setBusyPoints] = useState<ReadonlySet<number>>(new Set());
  const [applying, setApplying] = useState(false);
  const running = useRef(false);
  /** Branches whose take-away call already succeeded here (never called again silently). */
  const generated = useRef(new Set<number>());

  const decisionOf = (b: Branch): Decision => decisions[b.id] ?? "later";

  const generate = useCallback(
    async (branchId: number, regenerate: boolean) => {
      if (running.current) return;
      running.current = true;
      setTakeaways((t) => ({ ...t, [branchId]: { loading: true, error: null } }));
      try {
        const next = await api.takeaway(branchId, regenerate);
        generated.current.add(branchId);
        running.current = false;
        onState(next);
        setTakeaways((t) => ({ ...t, [branchId]: { loading: false, error: null } }));
      } catch (e) {
        running.current = false;
        const message = toApiError(e).message;
        setTakeaways((t) => ({ ...t, [branchId]: { loading: false, error: message } }));
      }
      onModelCall();
    },
    [onState, onModelCall],
  );

  // Take-aways are generated one branch at a time, and only for branches marked Merge.
  useEffect(() => {
    if (running.current || applying) return;
    const next = open.find(
      (b) =>
        decisionOf(b) === "merge" &&
        b.messages.length > 0 &&
        b.points.length === 0 &&
        !takeaways[b.id]?.error &&
        !generated.current.has(b.id),
    );
    if (next) void generate(next.id, false);
  });

  const onPointBusy = useCallback((pointId: number, busy: boolean) => {
    setBusyPoints((set) => {
      if (set.has(pointId) === busy) return set;
      const next = new Set(set);
      if (busy) next.add(pointId);
      else next.delete(pointId);
      return next;
    });
  }, []);

  const retry = (branchId: number): void => {
    setTakeaways((t) => ({ ...t, [branchId]: { loading: false, error: null } }));
  };

  const regenerate = (branchId: number): void => {
    const ok = window.confirm(
      "Regenerate this take-away? The current points and your edits to them will be replaced.",
    );
    if (ok) void generate(branchId, true);
  };

  const mergeIds = open.filter((b) => decisionOf(b) === "merge").map((b) => b.id);
  const discardIds = open.filter((b) => decisionOf(b) === "discard").map((b) => b.id);
  const generating = Object.values(takeaways).some((t) => t.loading);
  const notReady = open.some((b) => decisionOf(b) === "merge" && b.points.length === 0);
  const unsaved = busyPoints.size > 0;
  const nothingToDo = mergeIds.length === 0 && discardIds.length === 0;
  const canApply = !applying && !generating && !notReady && !unsaved && !nothingToDo;

  const apply = async (): Promise<void> => {
    if (!canApply) return;
    setApplying(true);
    try {
      for (const id of discardIds) onState(await api.discardBranch(id));
      if (mergeIds.length > 0) onState(await api.merge(state.conversation.id, mergeIds));
      onApplied();
    } catch (e) {
      onError(e);
      setApplying(false);
    }
  };

  let hint = "";
  if (applying) hint = "Applying…";
  else if (generating) hint = "Generating take-aways…";
  else if (notReady) hint = "A branch marked Merge has no take-away yet.";
  else if (unsaved) hint = "Saving your edits…";
  else if (nothingToDo) hint = "Choose Merge or Discard for at least one branch.";
  else {
    const parts: string[] = [];
    if (mergeIds.length > 0) parts.push(`merge ${mergeIds.length}`);
    if (discardIds.length > 0) parts.push(`discard ${discardIds.length}`);
    hint = `Will ${parts.join(" and ")}.`;
  }

  return (
    <Modal
      title="Merge branches"
      wide
      onClose={onClose}
      footer={
        <>
          <span className="modal-hint" role="status">
            {hint}
          </span>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canApply}
            onClick={() => void apply()}
          >
            Apply
          </button>
        </>
      }
    >
      <p className="muted merge-intro">
        Only the checked points enter the main context. Branches left on “Decide later” stay open
        and out of the context.
      </p>
      {open.length === 0 && <p>There are no open branches.</p>}
      {open.map((b) => (
        <MergeBranchCard
          key={b.id}
          branch={b}
          decision={decisionOf(b)}
          takeaway={takeaways[b.id] ?? null}
          anyGenerating={generating}
          locked={applying}
          onDecision={(d) => setDecisions((all) => ({ ...all, [b.id]: d }))}
          onRetry={() => retry(b.id)}
          onRegenerate={() => regenerate(b.id)}
          onState={onState}
          onError={onError}
          onPointBusy={onPointBusy}
        />
      ))}
    </Modal>
  );
}
