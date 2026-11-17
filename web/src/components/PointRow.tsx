import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import type { ConversationState, Point, PointUpdate } from "../types";

interface Props {
  point: Point;
  disabled: boolean;
  onState: (state: ConversationState) => void;
  onError: (error: unknown) => void;
  /** Tells the dialog that this row has an unsaved edit or a save in flight. */
  onBusy: (pointId: number, busy: boolean) => void;
}

const AUTOSAVE_MS = 900;

/** One take-away point: checkbox + title, expandable to edit the text that enters the context. */
export function PointRow({ point, disabled, onState, onError, onBusy }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(point.text_final);
  const [saving, setSaving] = useState(false);
  /** The text of the last save we sent: when it comes back, the draft is left alone. */
  const sent = useRef<string | null>(null);
  const textId = useId();
  const dirty = draft !== point.text_final;

  // The server text changed for another reason (reset, another save): show it.
  useEffect(() => {
    if (point.text_final !== sent.current) setDraft(point.text_final);
    sent.current = null;
  }, [point.text_final]);

  useEffect(() => {
    onBusy(point.id, dirty || saving);
  }, [onBusy, point.id, dirty, saving]);
  useEffect(() => () => onBusy(point.id, false), [onBusy, point.id]);

  const patch = async (update: PointUpdate): Promise<void> => {
    setSaving(true);
    try {
      onState(await api.patchPoint(point.id, update));
    } catch (e) {
      sent.current = null;
      onError(e);
    } finally {
      setSaving(false);
    }
  };

  const saveText = (revertIfBlank: boolean): void => {
    if (!dirty || saving) return;
    if (draft.trim() === "") {
      if (revertIfBlank) setDraft(point.text_final);
      return;
    }
    sent.current = draft;
    void patch({ text_final: draft });
  };

  // Autosave shortly after the last keystroke; leaving the field saves at once.
  const saveRef = useRef(saveText);
  saveRef.current = saveText;
  useEffect(() => {
    if (!dirty || saving) return;
    const timer = window.setTimeout(() => saveRef.current(false), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, dirty, saving]);

  const byUser = point.origin === "user";
  const edited = !byUser && point.text_final !== point.text_generated;
  const [titleDraft, setTitleDraft] = useState(point.title);
  useEffect(() => setTitleDraft(point.title), [point.title]);

  const saveTitle = (): void => {
    const next = titleDraft.trim();
    if (!next || next === point.title) {
      setTitleDraft(point.title);
      return;
    }
    void patch({ title: next });
  };

  const remove = async (): Promise<void> => {
    setSaving(true);
    try {
      onState(await api.deletePoint(point.id));
    } catch (e) {
      onError(e);
      setSaving(false);
    }
  };

  return (
    <li className={`point${point.included ? "" : " point-excluded"}`}>
      <div className="point-head">
        <label className="point-check">
          <input
            type="checkbox"
            checked={point.included}
            disabled={disabled || saving}
            onChange={() => void patch({ included: !point.included })}
          />
          <span className="point-title">{point.title}</span>
        </label>
        {edited && <span className="point-edited">Edited</span>}
        {byUser && <span className="point-edited">Added by you</span>}
        <button
          type="button"
          className="icon-btn chevron"
          aria-expanded={expanded}
          aria-controls={textId}
          aria-label={`${expanded ? "Hide" : "Show"} the text of “${point.title}”`}
          onClick={() => setExpanded((v) => !v)}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M4 6l4 4 4-4" />
          </svg>
        </button>
      </div>
      {expanded && (
        <div className="point-body" id={textId}>
          <input
            type="text"
            className="point-title-input"
            aria-label={`Title of “${point.title}”`}
            value={titleDraft}
            disabled={disabled || saving}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.currentTarget.blur();
              }
            }}
          />
          <textarea
            aria-label={`Text of “${point.title}” that enters the context`}
            value={draft}
            rows={Math.min(8, Math.max(2, Math.ceil(draft.length / 70)))}
            disabled={disabled}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => saveText(true)}
          />
          <div className="point-meta">
            <span className="muted">
              {saving ? "Saving…" : dirty ? "Unsaved" : "This text enters the main context."}
            </span>
            {edited && (
              <button
                type="button"
                className="link-btn"
                disabled={disabled || saving}
                onClick={() => void patch({ text_final: point.text_generated })}
              >
                Reset to generated
              </button>
            )}
            {byUser && (
              <button
                type="button"
                className="link-btn link-danger"
                disabled={disabled || saving}
                onClick={() => void remove()}
              >
                Delete point
              </button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
