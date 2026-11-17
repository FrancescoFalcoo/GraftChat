import { afterEach, describe, expect, it, vi } from "vitest";
import { isSoundOn, playGlop, setSoundOn } from "../sound";

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

/** A fake AudioContext that records the oscillators it creates. */
function fakeAudio() {
  const started: number[] = [];
  const param = () => ({
    value: 0,
    setValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
  });
  const node = () => ({ gain: param(), connect: vi.fn((n: unknown) => n) });
  class FakeContext {
    state = "running";
    currentTime = 0;
    destination = {};
    resume = vi.fn();
    createGain = vi.fn(node);
    createOscillator = vi.fn(() => ({
      type: "",
      frequency: param(),
      connect: vi.fn((n: unknown) => n),
      start: vi.fn((t: number) => started.push(t)),
      stop: vi.fn(),
    }));
  }
  vi.stubGlobal("AudioContext", FakeContext);
  return started;
}

describe("sound", () => {
  it("is on by default and remembers being switched off", () => {
    expect(isSoundOn()).toBe(true);
    setSoundOn(false);
    expect(isSoundOn()).toBe(false);
    setSoundOn(true);
    expect(isSoundOn()).toBe(true);
  });

  it("plays one drop for a branch and two for a merge", () => {
    const started = fakeAudio();
    playGlop("branch");
    expect(started.length).toBe(2); // one drop = two partials
    playGlop("merge");
    expect(started.length).toBe(6);
  });

  it("stays silent when switched off or when audio is missing", () => {
    const started = fakeAudio();
    setSoundOn(false);
    playGlop("merge");
    expect(started.length).toBe(0);

    setSoundOn(true);
    vi.stubGlobal("AudioContext", undefined);
    expect(() => playGlop("merge")).not.toThrow();
  });
});
