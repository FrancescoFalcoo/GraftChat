import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { ACCEPT, fileKind, fileProblem, filesOf, formatSize, type FileKind } from "../files";

interface Props {
  label: string;
  placeholder: string;
  disabled: boolean;
  /** Resolves to false when the message was not stored: text and files are put back. */
  onSend: (text: string, files: File[]) => Promise<boolean>;
  /** Take the focus when it appears (a branch just opened: one starts typing at once). */
  autoFocus?: boolean;
}

const MAX_HEIGHT = 200;

interface Picked {
  file: File;
  kind: FileKind;
  url: string | null; // object URL of an image's thumbnail
  key: string;
}

let nextKey = 0;

export function Composer({ label, placeholder, disabled, onSend, autoFocus = false }: Props) {
  const [value, setValue] = useState("");
  const [picked, setPicked] = useState<Picked[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const wasDisabled = useRef(disabled);
  const pickedRef = useRef(picked);
  pickedRef.current = picked;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  useEffect(() => {
    if (!autoFocus) return;
    // After the selection popover and the panel's own effects have settled.
    const timer = window.setTimeout(() => ref.current?.focus({ preventScroll: true }), 0);
    return () => window.clearTimeout(timer);
  }, []);

  // Give the focus back once the reply arrived, unless the user went elsewhere.
  useEffect(() => {
    if (wasDisabled.current && !disabled && document.activeElement === document.body) {
      ref.current?.focus();
    }
    wasDisabled.current = disabled;
  }, [disabled]);

  // Thumbnails still on screen when the composer goes away.
  useEffect(
    () => () =>
      pickedRef.current.forEach((p) => {
        if (p.url) URL.revokeObjectURL(p.url);
      }),
    [],
  );

  const addFiles = (files: File[]): void => {
    if (files.length === 0) return;
    let next = pickedRef.current;
    let firstProblem: string | null = null;
    for (const file of files) {
      const counts = { images: next.filter((p) => p.kind === "image").length, total: next.length };
      const why = fileProblem(file, counts);
      const kind = fileKind(file);
      if (why || kind === null) {
        firstProblem ??= why;
        continue;
      }
      const url = kind === "image" ? URL.createObjectURL(file) : null;
      next = [...next, { file, kind, url, key: `f${nextKey++}` }];
    }
    setPicked(next);
    setProblem(firstProblem);
  };

  const remove = (key: string): void => {
    const gone = picked.find((p) => p.key === key);
    if (gone?.url) URL.revokeObjectURL(gone.url);
    setPicked(picked.filter((p) => p.key !== key));
    setProblem(null);
  };

  const submit = async (): Promise<void> => {
    const text = value.trim();
    if ((!text && picked.length === 0) || disabled) return;
    const sent = picked;
    setValue("");
    setPicked([]);
    setProblem(null);
    const stored = await onSend(
      text,
      sent.map((p) => p.file),
    );
    if (stored) {
      sent.forEach((p) => {
        if (p.url) URL.revokeObjectURL(p.url);
      });
      return;
    }
    setValue((current) => (current === "" ? text : current));
    setPicked((current) => (current.length === 0 ? sent : current));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>): void => {
    const files = filesOf(e.clipboardData.files);
    if (files.length === 0) return; // plain text: the browser pastes it
    e.preventDefault();
    addFiles(files);
  };

  const onDrop = (e: DragEvent<HTMLFormElement>): void => {
    setDragging(false);
    const files = filesOf(e.dataTransfer.files);
    if (files.length === 0 || disabled) return;
    e.preventDefault();
    addFiles(files);
  };

  const empty = value.trim() === "" && picked.length === 0;

  return (
    <form
      className="composer"
      data-dragging={dragging ? "" : undefined}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      onDragOver={(e) => {
        if (disabled || !Array.from(e.dataTransfer.types).includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {(picked.length > 0 || problem) && (
        <div className="attach-tray">
          {picked.map((p) =>
            p.url ? (
              <figure key={p.key} className="attach-thumb">
                <img src={p.url} alt={p.file.name} />
                <button
                  type="button"
                  className="attach-remove"
                  aria-label={`Remove ${p.file.name}`}
                  onClick={() => remove(p.key)}
                >
                  ×
                </button>
              </figure>
            ) : (
              <span key={p.key} className="attach-doc" title={p.file.name}>
                <DocIcon />
                <span className="attach-doc-name">{p.file.name}</span>
                <span className="attach-doc-size">{formatSize(p.file.size)}</span>
                <button
                  type="button"
                  className="attach-remove attach-remove-inline"
                  aria-label={`Remove ${p.file.name}`}
                  onClick={() => remove(p.key)}
                >
                  ×
                </button>
              </span>
            ),
          )}
          {problem && (
            <p className="attach-problem" role="alert">
              {problem}
            </p>
          )}
        </div>
      )}
      <button
        type="button"
        className="btn btn-small composer-attach"
        aria-label="Attach files"
        title="Attach images, PDF, Word or text files (or paste / drop them here)"
        disabled={disabled}
        onClick={() => fileRef.current?.click()}
      >
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          <path
            d="M10.5 4.5 5.8 9.2a1.4 1.4 0 0 0 2 2l5-5a2.8 2.8 0 0 0-4-4l-5 5a4.2 4.2 0 0 0 6 6l4.2-4.2"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          addFiles(Array.from(e.target.files ?? []));
          e.target.value = ""; // the same file can be picked again after removing it
        }}
      />
      <textarea
        ref={ref}
        aria-label={label}
        rows={1}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
      />
      <button type="submit" className="btn btn-primary" disabled={disabled || empty}>
        Send
      </button>
    </form>
  );
}

export function DocIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" className="doc-icon">
      <path
        d="M4 1.5h5.2L12.5 4.8v9.7h-8.5zM9 1.5v3.5h3.5M6 8h4.5M6 10.5h4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  );
}
