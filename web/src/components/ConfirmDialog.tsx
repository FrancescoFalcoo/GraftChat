import { Modal } from "./Modal";

interface Props {
  title: string;
  message: string;
  confirmLabel: string;
  /** Styles the confirm button as destructive (red). */
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A yes/no question in the app's own dialog, instead of the browser's confirm(). */
export function ConfirmDialog({ title, message, confirmLabel, danger = false, onConfirm, onCancel }: Props) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${danger ? "btn-danger-solid" : "btn-primary"}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="confirm-text">{message}</p>
    </Modal>
  );
}
