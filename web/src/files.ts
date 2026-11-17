import type { FileUpload } from "./types";

// The same rules as the server (api/service.py, api/documents.py): checked here too so the
// user learns at once, before anything is uploaded. The server has the last word.
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
export const MAX_FILES = 6;
export const MAX_IMAGES = 4;
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;

/** Plain text and source code, by extension (mirrors api/documents.py TEXT_EXTENSIONS). */
const TEXT_EXTENSIONS = new Set(
  `txt text md markdown rst org csv tsv json jsonl yaml yml toml ini cfg conf env log xml
  html htm css scss less js mjs cjs jsx ts tsx vue svelte py pyi ipynb java kt kts scala
  groovy c h cc cpp cxx hpp hh cs go rs rb php pl pm swift m mm r jl lua dart ex exs erl
  hs ml fs clj sql sh bash zsh fish ps1 bat cmd dockerfile makefile gradle tex bib srt vtt`.split(/\s+/),
);

export const ACCEPT = [
  ...IMAGE_TYPES,
  ".pdf",
  ".docx",
  ...Array.from(TEXT_EXTENSIONS, (e) => `.${e}`),
].join(",");

export type FileKind = "image" | "document";

function extension(name: string): string {
  const lower = name.toLowerCase();
  const dot = lower.lastIndexOf(".");
  return dot >= 0 ? lower.slice(dot + 1) : lower;
}

/** What a file will be sent as, or null when it cannot be sent at all. */
export function fileKind(file: File): FileKind | null {
  if (IMAGE_TYPES.includes(file.type)) return "image";
  const ext = extension(file.name);
  if (ext === "pdf" || ext === "docx" || TEXT_EXTENSIONS.has(ext)) return "document";
  if (file.type.startsWith("text/")) return "document";
  return null;
}

/** Why `file` cannot join the files already picked, or null if it can. */
export function fileProblem(file: File, picked: { images: number; total: number }): string | null {
  const kind = fileKind(file);
  if (kind === null) return `${file.name}: images, PDF, Word (.docx), or plain text and code only.`;
  if (picked.total >= MAX_FILES) return `At most ${MAX_FILES} files per message.`;
  if (kind === "image") {
    if (file.size > MAX_IMAGE_BYTES) return `${file.name} is larger than 5 MB.`;
    if (picked.images >= MAX_IMAGES) return `At most ${MAX_IMAGES} images per message.`;
  } else if (file.size > MAX_DOCUMENT_BYTES) {
    return `${file.name} is larger than 10 MB.`;
  }
  return null;
}

/** A file as the API wants it: base64 without the "data:…;base64," prefix. */
export function toUpload(file: File): Promise<FileUpload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const url = String(reader.result);
      resolve({ name: file.name || "file", mime: file.type, data: url.slice(url.indexOf(",") + 1) });
    };
    reader.readAsDataURL(file);
  });
}

/** The files of a paste or a drop. */
export function filesOf(list: FileList | null | undefined): File[] {
  return Array.from(list ?? []);
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
