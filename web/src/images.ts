import type { ImageUpload } from "./types";

// The same limits as the server (api/service.py): checked here too so the user learns
// at once, before anything is uploaded.
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
export const MAX_IMAGES = 4;
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** Why `file` cannot be attached next to `already` others, or null if it can. */
export function imageProblem(file: File, already: number): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return `${file.name}: only PNG, JPEG, GIF and WebP images.`;
  if (file.size > MAX_IMAGE_BYTES) return `${file.name} is larger than 5 MB.`;
  if (already >= MAX_IMAGES) return `At most ${MAX_IMAGES} images per message.`;
  return null;
}

/** A file as the API wants it: base64 without the "data:…;base64," prefix. */
export function toUpload(file: File): Promise<ImageUpload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const url = String(reader.result);
      resolve({ name: file.name || "image", mime: file.type, data: url.slice(url.indexOf(",") + 1) });
    };
    reader.readAsDataURL(file);
  });
}

/** The image files of a paste or a drop. */
export function imageFiles(list: FileList | null | undefined): File[] {
  return Array.from(list ?? []).filter((f) => f.type.startsWith("image/"));
}
