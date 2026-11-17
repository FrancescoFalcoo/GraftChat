/**
 * Small "drop" sounds for the two moments that change the shape of a conversation:
 * opening a branch (a light, rising "plip") and merging (a rounder, falling "glop").
 *
 * Synthesised with the Web Audio API: no audio file, nothing downloaded. The sound can
 * be switched off; the choice is kept in this browser only.
 */

const STORAGE_KEY = "graftchat.sound";

export type SoundKind = "branch" | "merge";

let context: AudioContext | null = null;

export function isSoundOn(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundOn(on: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
  } catch {
    // Storage unavailable: the choice lasts until the page is reloaded.
  }
}

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!context) context = new Ctor();
  if (context.state === "suspended") void context.resume();
  return context;
}

/**
 * One water drop: a sine whose pitch glides quickly, with a fast attack and a short
 * decay, plus a quieter second partial for body.
 */
function drop(ctx: AudioContext, at: number, from: number, to: number, length: number, volume: number): void {
  const out = ctx.createGain();
  out.gain.setValueAtTime(0.0001, at);
  out.gain.exponentialRampToValueAtTime(volume, at + 0.006);
  out.gain.exponentialRampToValueAtTime(0.0001, at + length);
  out.connect(ctx.destination);

  for (const [ratio, level] of [
    [1, 1],
    [2.01, 0.18],
  ] as const) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(from * ratio, at);
    osc.frequency.exponentialRampToValueAtTime(to * ratio, at + length * 0.55);
    gain.gain.value = level;
    osc.connect(gain).connect(out);
    osc.start(at);
    osc.stop(at + length + 0.02);
  }
}

/** Plays the sound of an event, unless sounds are off or audio is unavailable. */
export function playGlop(kind: SoundKind): void {
  if (!isSoundOn()) return;
  try {
    const ctx = audio();
    if (!ctx) return;
    const now = ctx.currentTime + 0.01;
    if (kind === "branch") {
      drop(ctx, now, 520, 1250, 0.13, 0.22); // a light drop leaving: pitch goes up
    } else {
      drop(ctx, now, 900, 260, 0.2, 0.28); // a round "glop" landing: pitch falls
      drop(ctx, now + 0.09, 620, 340, 0.14, 0.12); // and a small splash after it
    }
  } catch {
    // Audio is a nicety: never let it break the action it accompanies.
  }
}
