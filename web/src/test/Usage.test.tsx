import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerUsageLine, BranchUsage, ChatUsage } from "../components/Usage";
import type { ConversationState } from "../types";
import { formatCost, UsageContext, type Usage } from "../usage";

const usage: Usage = {
  total: { calls: 3, input_tokens: 1500, output_tokens: 300, cost: 0.0042 },
  chat: { calls: 2, input_tokens: 1300, output_tokens: 220, cost: 0.003 },
  takeaway: { calls: 1, input_tokens: 200, output_tokens: 80, cost: 0.0012 },
  threads: [
    { branch_id: null, calls: 1, input_tokens: 1240, output_tokens: 180, cost: 0.002 },
    { branch_id: 7, calls: 2, input_tokens: 260, output_tokens: 120, cost: 0.0022 },
  ],
  messages: [{ message_id: 2, model: "vendor/chat", input_tokens: 1240, output_tokens: 180, cost: 0.002 }],
};

const state = {
  conversation: { id: 1, title: "t", created_at: "" },
  main: [],
  branches: [
    {
      id: 7,
      anchor_message_id: 2,
      anchor_start: 0,
      anchor_end: 4,
      anchor_quote: "AVIF or WebP",
      status: "open",
      merge_message_id: null,
      base_message_id: null,
      created_at: "",
      messages: [],
      points: [],
    },
  ],
  pending_branch_ids: [7],
  usage,
} as ConversationState;

describe("usage figures", () => {
  it("show what each answer sent and cost, the chat totals and the branch's", () => {
    render(
      <UsageContext.Provider value={usage}>
        <AnswerUsageLine messageId={2} />
        <ChatUsage state={state} />
        <BranchUsage branchId={7} />
      </UsageContext.Provider>,
    );
    expect(screen.getByText("1,240 tokens in, 180 out, $0.0020")).toBeTruthy();
    fireEvent.click(screen.getByText("1,800 tokens, $0.0042"));
    expect(screen.getByRole("table", { name: "Model calls in this chat" })).toBeTruthy();
    expect(screen.getByRole("rowheader", { name: /AVIF or WebP/ })).toBeTruthy();
    expect(screen.getByText(/This branch: 2 calls, 260 tokens in/)).toBeTruthy();
  });

  it("show nothing when hidden in Settings", () => {
    const { container } = render(
      <UsageContext.Provider value={null}>
        <AnswerUsageLine messageId={2} />
        <ChatUsage state={state} />
        <BranchUsage branchId={7} />
      </UsageContext.Provider>,
    );
    expect(container.textContent).toBe("");
  });

  it("call a free call free", () => {
    expect(formatCost(0)).toBe("free");
    expect(formatCost(0.25)).toBe("$0.25");
  });
});
