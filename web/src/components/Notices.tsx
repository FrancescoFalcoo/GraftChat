import { useState } from "react";
import type { Toast } from "../hooks/useToasts";
import type { Health } from "../types";
import { plural } from "../util";

interface BannerProps {
  count: number;
  onReview: () => void;
  onDismiss: () => void;
}

/** "You came back from N branches" banner shown above the main composer. */
export function ReturnBanner({ count, onReview, onDismiss }: BannerProps) {
  return (
    <div className="return-banner" role="status">
      <span>
        You came back from {plural(count, "branch")}. Merge?
      </span>
      <button type="button" className="btn btn-small btn-primary" onClick={onReview}>
        Review &amp; merge
      </button>
      <button type="button" className="icon-btn" aria-label="Dismiss" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
}

/** Thin strip listing the core functions that are still stubs. */
export function DevNotice({ health }: { health: Health | null }) {
  const [dismissed, setDismissed] = useState(false);
  const missing = health ? Object.keys(health.core).filter((name) => !health.core[name]) : [];
  if (dismissed || missing.length === 0) return null;
  return (
    <div className="dev-notice" role="status">
      <span>
        Core functions not implemented yet: {missing.join(", ")}. Some features will return
        errors.
      </span>
      <button
        type="button"
        className="icon-btn"
        aria-label="Dismiss notice"
        onClick={() => setDismissed(true)}
      >
        ×
      </button>
    </div>
  );
}

interface ToastsProps {
  toasts: Toast[];
  onDismiss: (id: number) => void;
  onOpenSettings: () => void;
}

export function Toasts({ toasts, onDismiss, onOpenSettings }: ToastsProps) {
  return (
    <div className="toasts" aria-live="assertive" aria-atomic="false">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <p>{t.message}</p>
          <div className="toast-actions">
            {t.offerSettings && (
              <button
                type="button"
                className="btn btn-small"
                onClick={() => {
                  onOpenSettings();
                  onDismiss(t.id);
                }}
              >
                Open settings
              </button>
            )}
            <button
              type="button"
              className="icon-btn"
              aria-label={t.kind === "error" ? "Dismiss error" : "Dismiss"}
              onClick={() => onDismiss(t.id)}
            >
              ×
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
