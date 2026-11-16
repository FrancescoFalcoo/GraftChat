import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface Props {
  label: string;
  placeholder: string;
  disabled: boolean;
  /** Resolves to false when the text was not stored: it is put back in the box. */
  onSend: (text: string) => Promise<boolean>;
}

const MAX_HEIGHT = 200;

export function Composer({ label, placeholder, disabled, onSend }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const wasDisabled = useRef(disabled);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  // Give the focus back once the reply arrived, unless the user went elsewhere.
  useEffect(() => {
    if (wasDisabled.current && !disabled && document.activeElement === document.body) {
      ref.current?.focus();
    }
    wasDisabled.current = disabled;
  }, [disabled]);

  const submit = async (): Promise<void> => {
    const text = value.trim();
    if (!text || disabled) return;
    setValue("");
    const stored = await onSend(text);
    if (!stored) setValue((current) => (current === "" ? text : current));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <textarea
        ref={ref}
        aria-label={label}
        rows={1}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button
        type="submit"
        className="btn btn-primary"
        disabled={disabled || value.trim() === ""}
      >
        Send
      </button>
    </form>
  );
}
