import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { IMAGE_TYPES, imageFiles, imageProblem } from "../images";

interface Props {
  label: string;
  placeholder: string;
  disabled: boolean;
  /** Resolves to false when the message was not stored: text and images are put back. */
  onSend: (text: string, images: File[]) => Promise<boolean>;
}

const MAX_HEIGHT = 200;

interface Picked {
  file: File;
  url: string; // object URL for the thumbnail
}

export function Composer({ label, placeholder, disabled, onSend }: Props) {
  const [value, setValue] = useState("");
  const [images, setImages] = useState<Picked[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const wasDisabled = useRef(disabled);
  const imagesRef = useRef(images);
  imagesRef.current = images;

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

  // Thumbnails still on screen when the composer goes away.
  useEffect(() => () => imagesRef.current.forEach((p) => URL.revokeObjectURL(p.url)), []);

  const addFiles = (files: File[]): void => {
    if (files.length === 0) return;
    let next = imagesRef.current;
    let firstProblem: string | null = null;
    for (const file of files) {
      const why = imageProblem(file, next.length);
      if (why) {
        firstProblem ??= why;
        continue;
      }
      next = [...next, { file, url: URL.createObjectURL(file) }];
    }
    setImages(next);
    setProblem(firstProblem);
  };

  const remove = (index: number): void => {
    const gone = images[index];
    if (gone) URL.revokeObjectURL(gone.url);
    setImages(images.filter((_, i) => i !== index));
    setProblem(null);
  };

  const submit = async (): Promise<void> => {
    const text = value.trim();
    if ((!text && images.length === 0) || disabled) return;
    const sent = images;
    setValue("");
    setImages([]);
    setProblem(null);
    const stored = await onSend(
      text,
      sent.map((p) => p.file),
    );
    if (stored) {
      sent.forEach((p) => URL.revokeObjectURL(p.url));
      return;
    }
    setValue((current) => (current === "" ? text : current));
    setImages((current) => (current.length === 0 ? sent : current));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>): void => {
    const files = imageFiles(e.clipboardData.files);
    if (files.length === 0) return; // plain text: the browser pastes it
    e.preventDefault();
    addFiles(files);
  };

  const onDrop = (e: DragEvent<HTMLFormElement>): void => {
    setDragging(false);
    const files = imageFiles(e.dataTransfer.files);
    if (files.length === 0 || disabled) return;
    e.preventDefault();
    addFiles(files);
  };

  const empty = value.trim() === "" && images.length === 0;

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
      {(images.length > 0 || problem) && (
        <div className="attach-tray">
          {images.map((p, i) => (
            <figure key={p.url} className="attach-thumb">
              <img src={p.url} alt={p.file.name} />
              <button
                type="button"
                className="attach-remove"
                aria-label={`Remove ${p.file.name}`}
                onClick={() => remove(i)}
              >
                ×
              </button>
            </figure>
          ))}
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
        aria-label="Attach images"
        title="Attach images (or paste / drop them here)"
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
        accept={IMAGE_TYPES.join(",")}
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
