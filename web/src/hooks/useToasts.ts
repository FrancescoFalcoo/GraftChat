import { useCallback, useRef, useState } from "react";
import { toApiError } from "../api";

export interface Toast {
  id: number;
  message: string;
  /** Set for errors that are fixed in the settings (missing key or model). */
  offerSettings: boolean;
}

const MAX_TOASTS = 4;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const pushError = useCallback((error: unknown) => {
    const err = toApiError(error);
    const toast: Toast = {
      id: nextId.current++,
      message: err.message,
      offerSettings: err.code === "no_api_key" || err.code === "no_model",
    };
    setToasts((list) =>
      [...list.filter((t) => t.message !== toast.message), toast].slice(-MAX_TOASTS),
    );
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  return { toasts, pushError, dismissToast };
}
