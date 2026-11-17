import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationMap } from "../components/ConversationMap";
import { COL_W, layoutConversationMap, PAD, ROW_H, shortLabel } from "../conversationMap";
import { pickAnchorAt } from "../hooks/useAnchorClicks";
import type { Branch, ConversationState, Message } from "../types";

const NOW = "2026-11-17T10:00:00Z";

function message(id: number, role: Message["role"], content: string, branchId: number | null = null): Message {
  return { id, branch_id: branchId, parent_id: null, role, content, created_at: NOW };
}

function branch(id: number, anchor: number, quote: string, extra: Partial<Branch> = {}): Branch {
  return {
    id,
    anchor_message_id: anchor,
    anchor_start: 0,
    anchor_end: quote.length,
    anchor_quote: quote,
    status: "open",
    merge_message_id: null,
    created_at: NOW,
    messages: [],
    points: [],
    ...extra,
  };
}

/**
 * The sketch: "ciao" → "napoleone"; from napoleone's answer a branch merged back at the
 * merge node (two prompts), another merged one (one prompt), an open one (three prompts);
 * then "guru", "vita", and an empty discarded branch on vita's answer.
 */
function state(): ConversationState {
  return {
    conversation: { id: 1, title: "Sketch", created_at: NOW },
    main: [
      message(1, "user", "ciao"),
      message(2, "assistant", "hi"),
      message(3, "user", "napoleone"),
      message(4, "assistant", "**alto** and more"),
      message(5, "merge", ""),
      message(6, "user", "guru"),
      message(7, "assistant", "ok"),
      message(8, "user", "vita"),
      message(9, "assistant", "life"),
    ],
    branches: [
      branch(10, 4, "**alto**", {
        status: "merged",
        merge_message_id: 5,
        messages: [message(100, "user", "alto", 10), message(101, "user", "più alto", 10)],
      }),
      branch(20, 4, "and", {
        status: "merged",
        merge_message_id: 5,
        messages: [message(200, "user", "viola", 20)],
      }),
      branch(30, 4, "more", {
        messages: [message(300, "user", "cibo", 30), message(301, "user", "cane", 30), message(302, "user", "bav", 30)],
      }),
      branch(40, 9, "life", { status: "discarded" }),
    ],
    pending_branch_ids: [30],
  };
}

afterEach(cleanup);

describe("shortLabel", () => {
  it("keeps the first words and marks the cut", () => {
    expect(shortLabel("Explain grafting in three short points please")).toBe("Explain grafting in three…");
    expect(shortLabel("  Short   one\n")).toBe("Short one");
    expect(shortLabel("")).toBe("(empty)");
    expect(Array.from(shortLabel("x".repeat(200))).length).toBeLessThanOrEqual(31);
  });
});

describe("layoutConversationMap", () => {
  const layout = layoutConversationMap(state());
  const node = (key: string) => layout.nodes.find((n) => n.key === key)!;
  const trunkX = node("main-1").x;

  it("puts main on one vertical trunk, in order", () => {
    const main = ["main-1", "main-3", "main-5", "main-6", "main-8"].map(node);
    expect(new Set(main.map((n) => n.x))).toEqual(new Set([trunkX]));
    for (let i = 1; i < main.length; i++) expect(main[i].y).toBeGreaterThan(main[i - 1].y);
    expect(node("main-5").kind).toBe("merge");
  });

  it("stretches the trunk so a merged branch fits between its anchor and its merge node", () => {
    const anchorY = node("main-3").y;
    const mergeY = node("main-5").y;
    for (const key of ["branch-10-100", "branch-10-101", "branch-20-200"]) {
      expect(node(key).y).toBeGreaterThan(anchorY);
      expect(node(key).y).toBeLessThan(mergeY);
    }
    expect(mergeY - anchorY).toBe(3 * ROW_H); // two prompts + the merge row
  });

  it("gives overlapping branches different columns: left first, then right", () => {
    const xs = [node("branch-10-100").x, node("branch-20-200").x, node("branch-30-300").x];
    expect(new Set(xs).size).toBe(3);
    expect(xs[0]).toBe(trunkX - COL_W);
    expect(xs[1]).toBe(trunkX + COL_W);
    expect(xs[2]).toBe(trunkX + 2 * COL_W);
  });

  it("lets an open branch run on, and reuses a column once it is free", () => {
    expect(node("branch-30-302").y).toBe(node("main-3").y + 3 * ROW_H);
    const empty = node("empty-40");
    expect(empty.kind).toBe("empty");
    expect(empty.x).toBe(trunkX - COL_W); // the left column is free again after the merge
  });

  it("draws merged branches back into the trunk and the others as open ends", () => {
    const edge = (id: number) => layout.edges.find((e) => e.key === `branch-${id}`)!.d;
    const mergePoint = `${trunkX} ${node("main-5").y}`;
    expect(edge(10).endsWith(mergePoint)).toBe(true);
    expect(edge(30).endsWith(mergePoint)).toBe(false);
    expect(layout.edges.find((e) => e.key === "trunk")).toBeTruthy();
  });

  it("is empty for an empty conversation", () => {
    const empty = layoutConversationMap({ ...state(), main: [], branches: [] });
    expect(empty.nodes).toEqual([]);
    expect(empty.height).toBe(2 * PAD);
  });
});

describe("ConversationMap", () => {
  it("jumps to a main prompt, a branch prompt, a merge, and opens a branch", () => {
    const onJump = vi.fn();
    const onOpenBranch = vi.fn();
    render(<ConversationMap state={state()} onJump={onJump} onOpenBranch={onOpenBranch} onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Conversation map" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to: guru" }));
    expect(onJump).toHaveBeenLastCalledWith(6, null);
    fireEvent.click(screen.getByRole("button", { name: "Go to: cane" }));
    expect(onJump).toHaveBeenLastCalledWith(301, 30);
    fireEvent.click(screen.getByRole("button", { name: "Go to this merge" }));
    expect(onJump).toHaveBeenLastCalledWith(5, null);
    fireEvent.click(screen.getByRole("button", { name: "Open the branch on «alto» (merged)" }));
    expect(onOpenBranch).toHaveBeenLastCalledWith(10);
    fireEvent.click(screen.getByRole("button", { name: "Go to: Branch on «life», no messages yet" }));
    expect(onOpenBranch).toHaveBeenLastCalledWith(40);
  });

  it("says so when there is nothing to map", () => {
    render(
      <ConversationMap state={{ ...state(), main: [], branches: [] }} onJump={() => {}} onOpenBranch={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByText("Nothing here yet. Ask something first.")).toBeTruthy();
  });
});

describe("pickAnchorAt", () => {
  const box = (left: number, right: number) => ({ left, right, top: 0, bottom: 20 });

  it("finds the passage under the point", () => {
    const candidates = [{ branchId: 1, length: 10, order: 0, rects: [box(0, 100)] }];
    expect(pickAnchorAt(candidates, 50, 10)).toBe(1);
    expect(pickAnchorAt(candidates, 150, 10)).toBeNull();
    expect(pickAnchorAt(candidates, 50, 30)).toBeNull();
  });

  it("prefers the shortest overlapping passage, then the most recent", () => {
    const candidates = [
      { branchId: 1, length: 30, order: 0, rects: [box(0, 300)] },
      { branchId: 2, length: 5, order: 1, rects: [box(100, 150)] },
      { branchId: 3, length: 5, order: 2, rects: [box(100, 150)] },
    ];
    expect(pickAnchorAt(candidates, 120, 10)).toBe(3);
    expect(pickAnchorAt(candidates, 250, 10)).toBe(1);
  });
});
