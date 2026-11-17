import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationMap } from "../components/ConversationMap";
import { COL_W, layoutConversationMap, PAD, ROW_H, shortLabel } from "../conversationMap";
import { pickAnchorAt } from "../hooks/useAnchorClicks";
import type { Branch, ConversationState, Message } from "../types";

const NOW = "2026-11-17T10:00:00Z";

function message(id: number, role: Message["role"], content: string, branchId: number | null = null): Message {
  return { id, branch_id: branchId, parent_id: null, role, content, created_at: NOW, attachments: [] };
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
    base_message_id: null,
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
  const open = (name: string) => fireEvent.click(screen.getByRole("button", { name: `Details: ${name}` }));

  it("shows a block's details on click, and goes there only from the details", () => {
    const onJump = vi.fn();
    const onOpenBranch = vi.fn();
    render(<ConversationMap state={state()} onJump={onJump} onOpenBranch={onOpenBranch} onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Conversation map" })).toBeTruthy();
    open("guru");
    expect(onJump).not.toHaveBeenCalled();
    const details = screen.getByRole("region", { name: "Selected block" });
    expect(details.textContent).toContain("On main");
    expect(details.textContent).toContain("ok"); // the answer
    fireEvent.click(screen.getByRole("button", { name: "Go to this prompt" }));
    expect(onJump).toHaveBeenLastCalledWith(6, null);

    open("cane");
    expect(screen.getByRole("region", { name: "Selected block" }).textContent).toContain("In the branch on «more»");
    fireEvent.click(screen.getByRole("button", { name: "Go to this prompt" }));
    expect(onJump).toHaveBeenLastCalledWith(301, 30);
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect(onOpenBranch).toHaveBeenLastCalledWith(30);

    open("Merge");
    fireEvent.click(screen.getByRole("button", { name: "Go to this merge" }));
    expect(onJump).toHaveBeenLastCalledWith(5, null);

    open("Branch on «life», no messages yet");
    fireEvent.click(screen.getByRole("button", { name: "Open branch" }));
    expect(onOpenBranch).toHaveBeenLastCalledWith(40);
  });

  it("lists the branches that start from an answer on main", () => {
    render(<ConversationMap state={state()} onJump={() => {}} onOpenBranch={() => {}} onClose={() => {}} />);
    open("napoleone");
    const details = screen.getByRole("region", { name: "Selected block" });
    expect(details.textContent).toContain("Branches from this answer");
    expect(details.querySelectorAll(".node-branch-chip").length).toBe(3);
  });

  it("puts the passage on the first block of each branch, not on the curves", () => {
    render(<ConversationMap state={state()} onJump={() => {}} onOpenBranch={() => {}} onClose={() => {}} />);
    const quotes = [...document.querySelectorAll(".map-node-quote")].map((q) => q.textContent);
    expect(quotes).toEqual(["«alto»", "«and»", "«more»"]);
    expect(document.querySelector(".map-branch-label")).toBeNull();
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

describe("buildLogbook", () => {
  it("lists the first prompt, merges in order with kept and unticked points, open and discarded branches", async () => {
    const { buildLogbook } = await import("../logbook");
    const s = state();
    const pt = (id: number, branchId: number, position: number, included: boolean) => ({
      id,
      branch_id: branchId,
      position,
      title: `t${id}`,
      text_generated: `g${id}`,
      text_final: `f${id}`,
      included,
      origin: "model" as const,
    });
    s.branches[0].points = [pt(2, 10, 1, false), pt(1, 10, 0, true)];
    const log = buildLogbook(s);
    expect(log.start).toEqual({ messageId: 1, text: "ciao" });
    expect(log.prompts).toBe(4);
    expect(log.merges.map((m) => [m.number, m.branches.map((b) => b.id)])).toEqual([[1, [10, 20]]]);
    expect(log.merges[0].branches[0].kept.map((p) => p.id)).toEqual([1]);
    expect(log.merges[0].branches[0].left.map((p) => p.id)).toEqual([2]);
    expect(log.open.map((b) => b.id)).toEqual([30]);
    expect(log.discarded.map((b) => b.id)).toEqual([40]);
  });
});

describe("ConversationMap full screen", () => {
  it("has several ways out: Back to chat, Close map, the × and Escape", () => {
    const onClose = vi.fn();
    render(<ConversationMap state={state()} onJump={() => {}} onOpenBranch={() => {}} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Back to chat" }));
    for (const b of screen.getAllByRole("button", { name: "Close map" })) fireEvent.click(b);
    expect(onClose).toHaveBeenCalledTimes(3);
    fireEvent.keyDown(screen.getByRole("dialog", { name: "Conversation map" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it("closes the details first on Escape, then the map", () => {
    const onClose = vi.fn();
    render(<ConversationMap state={state()} onJump={() => {}} onOpenBranch={() => {}} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Details: guru" }));
    const dialog = screen.getByRole("dialog", { name: "Conversation map" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected block" })).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps each merged branch closed in the logbook until clicked", () => {
    const s = state();
    s.branches[0].points = [
      { id: 1, branch_id: 10, position: 0, title: "kept title", text_generated: "t", text_final: "kept text", included: true, origin: "model" },
    ];
    render(<ConversationMap state={s} onJump={() => {}} onOpenBranch={() => {}} onClose={() => {}} />);
    expect(screen.getByText("Merge 1")).toBeTruthy();
    expect(screen.queryByText("kept title")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /«alto».*1 point kept/ }));
    fireEvent.click(screen.getByRole("button", { name: "kept title" }));
    expect(screen.getByText("kept text")).toBeTruthy();
  });

  it("zooms with its buttons and marks where you are", () => {
    render(<ConversationMap state={state()} panelBranchId={30} onJump={() => {}} onOpenBranch={() => {}} onClose={() => {}} />);
    const value = () => screen.getByText(/^\d+%$/).textContent;
    const before = value();
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(value()).not.toBe(before);
    const current = document.querySelector(".map-node[data-current]");
    expect(current?.getAttribute("aria-label")).toBe("Details: bav"); // last prompt of the open branch
  });
});

describe("MiniMap", () => {
  it("draws only the shape of the tree, a dot per node, and opens the map", async () => {
    const { MiniMap } = await import("../components/MiniMap");
    const onToggle = vi.fn();
    render(<MiniMap state={state()} panelBranchId={null} open={false} onToggle={onToggle} />);
    expect(screen.queryByText("guru")).toBeNull();
    expect(document.querySelectorAll(".map-dot").length).toBe(layoutConversationMap(state()).nodes.length);
    expect(document.querySelectorAll(".map-dot[data-lane]").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Open the conversation map full screen" }));
    fireEvent.click(screen.getByRole("button", { name: "Open map" }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("says what will appear in an empty conversation", async () => {
    const { MiniMap } = await import("../components/MiniMap");
    render(<MiniMap state={{ ...state(), main: [], branches: [] }} panelBranchId={null} open={false} onToggle={() => {}} />);
    expect(screen.getByText(/appears here once you ask something/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open map" })).toHaveProperty("disabled", true);
  });
});
