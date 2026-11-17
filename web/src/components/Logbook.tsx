import { useState, type ReactNode } from "react";
import type { Logbook as LogbookData, LogbookBranch } from "../logbook";
import type { Point } from "../types";
import { readFlag, writeFlag } from "../util";

const SHOWN_KEY = "graftchat.logbookOpen";

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
        <Chevron />
      </button>
      {open && <p className="log-point-text">{point.text_final}</p>}
    </li>
  );
}

function Chevron() {
  return (
    <svg className="log-chevron" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M4 6l4 4 4-4" />
    </svg>
  );
}

/** One branch as a box in its own colour: closed by default, its points inside. */
function BranchBox({
  branch,
  summary,
  onShowBranch,
  children,
}: {
  branch: LogbookBranch;
  summary: string;
  onShowBranch: (id: number) => void;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="log-box" data-lane={branch.lane} data-open={open ? "" : undefined}>
      <button
        type="button"
        className="log-box-head"
        aria-expanded={open}
        onClick={() => {
          setOpen((v) => !v);
          onShowBranch(branch.id);
        }}
      >
        <span className="log-box-quote">«{branch.quote}»</span>
        <span className="log-box-meta">{summary}</span>
        <Chevron />
      </button>
      {open && <div className="log-box-body">{children}</div>}
    </div>
  );
}

function MergedBranch({ branch, onShowBranch }: { branch: LogbookBranch; onShowBranch: (id: number) => void }) {
  const [showLeft, setShowLeft] = useState(false);
  const kept = branch.kept.length;
  const summary = kept === 0 ? "nothing kept" : `${kept} point${kept === 1 ? "" : "s"} kept`;
  return (
    <BranchBox branch={branch} summary={summary} onShowBranch={onShowBranch}>
      {kept === 0 ? (
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
    </BranchBox>
  );
}

/** What the conversation established so far, from its merges: the map's companion. */
export function Logbook({ logbook, onShowBranch, onOpenBranch, onJump }: Props) {
  const { start, merges, open, discarded } = logbook;
  const [shown, setShown] = useState(() => readFlag(SHOWN_KEY, true));
  const toggle = (): void => {
    setShown((v) => {
      writeFlag(SHOWN_KEY, !v);
      return !v;
    });
  };
  const kept = merges.reduce((n, m) => n + m.branches.reduce((k, b) => k + b.kept.length, 0), 0);
  return (
    <div className="logbook" data-shown={shown ? "" : undefined}>
      <h2 className="log-title">
        <button type="button" className="log-title-toggle" aria-expanded={shown} onClick={toggle}>
          <Chevron />
          Logbook
          {!shown && (
            <span className="log-title-meta">
              {merges.length === 0
                ? "nothing merged yet"
                : `${merges.length} merge${merges.length === 1 ? "" : "s"}, ${kept} point${kept === 1 ? "" : "s"}`}
            </span>
          )}
        </button>
      </h2>
      {shown && (
        <>
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
              <p className="log-none">Nothing yet. When you merge a branch, the points you keep are listed here.</p>
            ) : (
              <ol className="log-merges">
                {merges.map((m) => (
                  <li key={m.messageId} className="log-merge">
                    <button type="button" className="log-merge-head" onClick={() => onJump(m.messageId)}>
                      Merge {m.number}
                    </button>
                    {m.branches.map((b) => (
                      <MergedBranch key={b.id} branch={b} onShowBranch={onShowBranch} />
                    ))}
                  </li>
                ))}
              </ol>
            )}
          </section>

          {open.length > 0 && (
            <section className="log-section">
              <h3>Still open</h3>
              {open.map((b) => (
                <BranchBox
                  key={b.id}
                  branch={b}
                  summary={b.prompts === 0 ? "no messages yet" : `${b.prompts} message${b.prompts === 1 ? "" : "s"}`}
                  onShowBranch={onShowBranch}
                >
                  <button type="button" className="btn btn-small" onClick={() => onOpenBranch(b.id)}>
                    Open branch
                  </button>
                </BranchBox>
              ))}
            </section>
          )}

          {discarded.length > 0 && (
            <section className="log-section">
              <h3>Discarded</h3>
              {discarded.map((b) => (
                <BranchBox key={b.id} branch={b} summary="discarded" onShowBranch={onShowBranch}>
                  <p className="log-none">It never entered the main context.</p>
                </BranchBox>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}
