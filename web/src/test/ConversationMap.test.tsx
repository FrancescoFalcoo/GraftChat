import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationMap } from "../components/ConversationMap";
import { buildConversationMap, shortLabel } from "../conversationMap";
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

/** Main: prompt 1, answer 2 (two branches on it), merge 3, prompt 4, answer 5. */
function state(): ConversationState {
  return {
    conversation: { id: 1, title: "Grafting", created_at: NOW },
    main: [
      message(1, "user", "Explain grafting in three short points please, thanks"),
      message(2, "assistant", "1. **First** point. 2. Second point."),
      message(3, "merge", ""),
      message(4, "user", "And now?"),
      message(5, "assistant", "Done."),
    ],
    branches: [
      branch(10, 2, "**First** point", {
        status: "merged",
        merge_message_id: 3,
        messages: [message(100, "user", "Why first?", 10), message(101, "assistant", "Because.", 10)],
      }),
      branch(20, 2, "Second point", { messages: [message(200, "user", "Tell me more", 20)] }),
    ],
    pending_branch_ids: [20],
  };
}

afterEach(cleanup);

describe("shortLabel", () => {
  it("keeps the first words and marks the cut", () => {
    expect(shortLabel("Explain grafting in three short points please, thanks")).toBe(
      "Explain grafting in three short points…",
    );
    expect(shortLabel("  Short   one\n")).toBe("Short one");
    expect(shortLabel("")).toBe("(empty)");
  });

  it("cuts a very long word", () => {
    expect(Array.from(shortLabel("x".repeat(200))).length).toBeLessThanOrEqual(49);
  });
});

describe("buildConversationMap", () => {
  it("lists main prompts in order, hangs branches under the prompt of their anchor", () => {
    const rows = buildConversationMap(state());
    expect(rows.map((r) => r.kind)).toEqual(["prompt", "merge", "prompt"]);

    const first = rows[0];
    if (first.kind !== "prompt") throw new Error("expected a prompt row");
    expect(first.prompt.messageId).toBe(1);
    expect(first.branches.map((b) => [b.id, b.lane, b.status, b.quote])).toEqual([
      [10, 0, "merged", "First point"],
      [20, 1, "open", "Second point"],
    ]);
    expect(first.branches[0].prompts.map((p) => p.messageId)).toEqual([100]);

    const merge = rows[1];
    if (merge.kind !== "merge") throw new Error("expected a merge row");
    expect(merge.merged.map((b) => b.id)).toEqual([10]);
  });

  it("is empty for an empty conversation", () => {
    expect(buildConversationMap({ ...state(), main: [], branches: [] })).toEqual([]);
  });
});

describe("ConversationMap", () => {
  it("jumps to a main prompt, a branch prompt, and opens a branch", () => {
    const onJump = vi.fn();
    const onOpenBranch = vi.fn();
    render(<ConversationMap state={state()} onJump={onJump} onOpenBranch={onOpenBranch} onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Conversation map" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to: And now?" }));
    expect(onJump).toHaveBeenLastCalledWith(4, null);

    fireEvent.click(screen.getByRole("button", { name: "Go to: Tell me more" }));
    expect(onJump).toHaveBeenLastCalledWith(200, 20);

    fireEvent.click(screen.getByRole("button", { name: "Open the branch on «Second point» (Open)" }));
    expect(onOpenBranch).toHaveBeenCalledWith(20);

    fireEvent.click(screen.getByRole("button", { name: "Go to this merge" }));
    expect(onJump).toHaveBeenLastCalledWith(3, null);
  });

  it("says so when there is nothing to map", () => {
    render(
      <ConversationMap
        state={{ ...state(), main: [], branches: [] }}
        onJump={() => {}}
        onOpenBranch={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("Nothing here yet. Ask something first.")).toBeTruthy();
  });
});
