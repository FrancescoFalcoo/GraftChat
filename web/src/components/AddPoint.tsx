import { useId, useState } from "react";
import { api } from "../api";
import type { ConversationState } from "../types";

interface Props {
  branchId: number;
  disabled: boolean;
  onState: (state: ConversationState) => void;
  onError: (error: unknown) => void;
}

/**
 * A point written by hand, next to the generated ones: something the model missed, a
 * different wording, or any text the user wants in the main context (DESIGN.md §14.14).
 */
export function AddPoint({ branchId, disabled, onState, onError }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const textId = useId();
  const titleId = useId();

  if (!open) {
    return (
      <button type="button" className="link-btn add-point-open" disabled={disabled} onClick={() => setOpen(true)}>
        + Add a point
      </button>
    );
  }

  const submit = async (): Promise<void> => {
    if (!text.trim() || saving) return;
    setSaving(true);
    try {
      onState(await api.addPoint(branchId, text.trim(), title.trim() || undefined));
      setText("");
      setTitle("");
      setOpen(false);
    } catch (e) {
      onError(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="add-point"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <label htmlFor={textId}>Text that enters the main context</label>
      <textarea
        id={textId}
        rows={3}
        value={text}
        autoFocus
        disabled={disabled || saving}
        placeholder="Something the take-away missed, or anything you want the model to know"
        onChange={(e) => setText(e.target.value)}
      />
      <label htmlFor={titleId}>Title in the checklist (optional, up to 5 words)</label>
      <input
        id={titleId}
        type="text"
        value={title}
        disabled={disabled || saving}
        placeholder="From the first words of the text"
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="add-point-actions">
        <button type="submit" className="btn btn-small btn-primary" disabled={disabled || saving || !text.trim()}>
          {saving ? "Adding…" : "Add point"}
        </button>
        <button
          type="button"
          className="btn btn-small"
          disabled={saving}
          onClick={() => {
            setOpen(false);
            setText("");
            setTitle("");
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
