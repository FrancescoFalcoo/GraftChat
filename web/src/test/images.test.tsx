import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "../components/Composer";
import { imageProblem, MAX_IMAGE_BYTES, MAX_IMAGES } from "../images";
import type { Branch, ConversationState, Message, Point } from "../types";
import { knownMerges } from "../util";

const NOW = "2026-11-17T10:00:00Z";

function message(id: number, role: Message["role"]): Message {
  return { id, branch_id: null, parent_id: null, role, content: `m${id}`, created_at: NOW, attachments: [] };
}

function point(branchId: number, included: boolean): Point {
  return { id: branchId * 10, branch_id: branchId, position: 0, title: "t", text_generated: "x", text_final: "x", included };
}

function branch(id: number, extra: Partial<Branch> = {}): Branch {
  return {
    id,
    anchor_message_id: 2,
    anchor_start: 0,
    anchor_end: 2,
    anchor_quote: `q${id}`,
    status: "open",
    merge_message_id: null,
    base_message_id: null,
    created_at: NOW,
    messages: [],
    points: [],
    ...extra,
  };
}

describe("knownMerges", () => {
  // main: 1 user, 2 answer, 3 merge (branch 10), 4 merge (branch 11)
  const main = [message(1, "user"), message(2, "assistant"), message(3, "merge"), message(4, "merge")];
  const merged10 = branch(10, { status: "merged", merge_message_id: 3, points: [point(10, true)] });
  const merged11 = branch(11, { status: "merged", merge_message_id: 4, points: [point(11, true)] });
  const empty12 = branch(12, { status: "merged", merge_message_id: 3, points: [point(12, false)] });

  function state(...extra: Branch[]): ConversationState {
    return {
      conversation: { id: 1, title: "c", created_at: NOW },
      main,
      branches: [merged10, merged11, empty12, ...extra],
      pending_branch_ids: [],
    };
  }

  it("counts the merges up to the base, with a ticked point", () => {
    const current = branch(20, { base_message_id: 3 });
    expect(knownMerges(state(current), current).map((b) => b.id)).toEqual([10]);
  });

  it("knows nothing merged after the anchor when there is no base", () => {
    const legacy = branch(21);
    expect(knownMerges(state(legacy), legacy)).toEqual([]);
  });

  it("sees every merge when opened at the end of main", () => {
    const late = branch(22, { base_message_id: 4 });
    expect(knownMerges(state(late), late).map((b) => b.id)).toEqual([10, 11]);
  });
});

describe("imageProblem", () => {
  const file = (type: string, size = 10) => new File([new Uint8Array(size)], "f", { type });

  it("accepts the supported types", () => {
    expect(imageProblem(file("image/png"), 0)).toBeNull();
    expect(imageProblem(file("image/webp"), MAX_IMAGES - 1)).toBeNull();
  });

  it("refuses other types, large files and too many images", () => {
    expect(imageProblem(file("image/svg+xml"), 0)).toMatch(/only PNG/);
    expect(imageProblem(file("image/png", MAX_IMAGE_BYTES + 1), 0)).toMatch(/5 MB/);
    expect(imageProblem(file("image/png"), MAX_IMAGES)).toMatch(/At most/);
  });
});

describe("Composer with images", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() }));
  });
  afterEach(cleanup);

  it("sends pasted images, and an image alone is enough to send", async () => {
    const onSend = vi.fn(async () => true);
    render(<Composer label="Message" placeholder="" disabled={false} onSend={onSend} />);
    const box = screen.getByLabelText("Message");
    const png = new File([new Uint8Array(4)], "shot.png", { type: "image/png" });
    fireEvent.paste(box, { clipboardData: { files: [png] } });

    expect(screen.getByAltText("shot.png")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith("", [png]));
    expect(screen.queryByAltText("shot.png")).toBeNull();
  });

  it("puts the images back when the message was not stored", async () => {
    const onSend = vi.fn(async () => false);
    render(<Composer label="Message" placeholder="" disabled={false} onSend={onSend} />);
    const png = new File([new Uint8Array(4)], "back.png", { type: "image/png" });
    fireEvent.paste(screen.getByLabelText("Message"), { clipboardData: { files: [png] } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(onSend).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByAltText("back.png")).toBeTruthy());
  });

  it("explains a refused file and keeps the others", () => {
    render(<Composer label="Message" placeholder="" disabled={false} onSend={vi.fn(async () => true)} />);
    const ok = new File([new Uint8Array(4)], "ok.png", { type: "image/png" });
    const bad = new File([new Uint8Array(4)], "bad.bmp", { type: "image/bmp" });
    fireEvent.paste(screen.getByLabelText("Message"), { clipboardData: { files: [ok, bad] } });
    expect(screen.getByAltText("ok.png")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/bad\.bmp/);
  });
});
