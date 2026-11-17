import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MergeNode } from "../components/MergeNode";
import type { Branch, Point } from "../types";

const NOW = "2026-11-17T10:00:00Z";

function point(id: number, title: string, included = true): Point {
  return { id, branch_id: 7, position: id, title, text_generated: "", text_final: `${title} text`, included, origin: "model" };
}

const branch: Branch = {
  id: 7,
  anchor_message_id: 2,
  anchor_start: 0,
  anchor_end: 10,
  anchor_quote: "Bruschette al pomodoro",
  status: "merged",
  merge_message_id: 9,
  base_message_id: null,
  created_at: NOW,
  messages: [],
  points: [point(1, "Aggiunto misto fritto"), point(2, "Quantità invariate"), point(3, "Left out", false)],
};

describe("MergeNode in the chat", () => {
  it("keeps the points folded until the branch is clicked", () => {
    const onOpenBranch = vi.fn();
    render(<MergeNode branches={[branch]} laneOf={() => 1} onOpenBranch={onOpenBranch} />);
    expect(screen.queryByText("Aggiunto misto fritto")).toBeNull();
    const head = screen.getByRole("button", { name: /Bruschette al pomodoro.*2 points brought back/ });
    expect(head.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(head);
    expect(screen.getByText("Aggiunto misto fritto")).toBeTruthy();
    expect(screen.queryByText("Left out")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open this branch" }));
    expect(onOpenBranch).toHaveBeenCalledWith(7);

    fireEvent.click(head);
    expect(screen.queryByText("Aggiunto misto fritto")).toBeNull();
  });
});
