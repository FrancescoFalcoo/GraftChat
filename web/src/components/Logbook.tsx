import { useState } from "react";
import type { Logbook as LogbookData, LogbookBranch } from "../logbook";
import type { Point } from "../types";

interface Props {
  logbook: LogbookData;
  /** Point the map at a branch. */
  onShowBranch: (branchId: number) => void;
  /** Open a branch in the side panel (closes the map). */
  onOpenBranch: (branchId: number) => void;
  /** Go to a message on main (closes the map). */
  onJump: (messageId: number) => void;
}

function PointItem({ point }: { point: Point }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="log-point">
      <button type="button" className="log-point-head" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="log-point-title">{point.title}</span>
        {point.origin === "user" && <span className="log-tag">yours</span>}
        <svg className="log-chevron" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>
      {open && <p className="log-point-text">{point.text_final}</p>}
    </li>
  );
}

function BranchItem({ branch, onShowBranch }: { branch: LogbookBranch; onShowBranch: (id: number) => void }) {
  const [showLeft, setShowLeft] = useState(false);
  return (
    <div className="log-branch" data-lane={branch.lane}>
      <button type="button" className="log-quote" title="Show on the map" onClick={() => onShowBranch(branch.id)}>
        «{branch.quote}»
      </button>
      {branch.kept.length === 0 ? (
        <p className="log-none">Merged with no point ticked: nothing entered the context.</p>
      ) : (
        <ul className="log-points">
          {branch.kept.map((p) => (
            <PointItem key={p.id} point={p} />
          ))}
        </ul>
      )}
      {branch.left.length > 0 && (
        <>
          <button type="button" className="link-btn log-left-toggle" aria-expanded={showLeft} onClick={() => setShowLeft((v) => !v)}>
            {showLeft ? "Hide" : "Show"} {branch.left.length} left out
          </button>
          {showLeft && (
            <ul className="log-points log-points-left">
              {branch.left.map((p) => (
                <PointItem key={p.id} point={p} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/** What the conversation established so far, from its merges: the map's companion. */
export function Logbook({ logbook, onShowBranch, onOpenBranch, onJump }: Props) {
  const { start, merges, open, discarded } = logbook;
  return (
    <div className="logbook">
      {start && (
        <section className="log-section">
          <h3>It started with</h3>
          <button type="button" className="log-start" onClick={() => onJump(start.messageId)}>
            {start.text}
          </button>
        </section>
      )}

      <section className="log-section">
        <h3>Brought back to main</h3>
        {merges.length === 0 ? (
          <p className="log-none">
            Nothing yet. When you merge a branch, the points you keep are listed here.
          </p>
        ) : (
          <ol className="log-merges">
            {merges.map((m) => (
              <li key={m.messageId} className="log-merge">
                <button type="button" className="log-merge-head" onClick={() => onJump(m.messageId)}>
                  Merge {m.number}
                </button>
                {m.branches.map((b) => (
                  <BranchItem key={b.id} branch={b} onShowBranch={onShowBranch} />
                ))}
              </li>
            ))}
          </ol>
        )}
      </section>

      {open.length > 0 && (
        <section className="log-section">
          <h3>Still open</h3>
          <ul className="log-open">
            {open.map((b) => (
              <li key={b.id} data-lane={b.lane}>
                <button type="button" className="log-quote" onClick={() => onOpenBranch(b.id)}>
                  «{b.quote}»
                </button>
                <span className="log-meta">
                  {b.prompts === 0 ? "no messages yet" : `${b.prompts} message${b.prompts === 1 ? "" : "s"}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {discarded.length > 0 && (
        <section className="log-section">
          <h3>Discarded</h3>
          <ul className="log-open log-discarded">
            {discarded.map((b) => (
              <li key={b.id} data-lane={b.lane}>
                <button type="button" className="log-quote" onClick={() => onShowBranch(b.id)}>
                  «{b.quote}»
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
