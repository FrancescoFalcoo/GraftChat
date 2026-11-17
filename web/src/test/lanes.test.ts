import { describe, expect, it } from "vitest";
import { layoutConversationMap } from "../conversationMap";
import { highlightName, highlightRules } from "../hooks/useAnchorHighlights";
import { branchColor, branchColors, branchNumber, generatedColor, POOL } from "../lanes";
import type { Branch, BranchStatus, ConversationState } from "../types";

function branch(id: number, created_at: string, status: BranchStatus = "open"): Branch {
  return {
    id,
    anchor_message_id: 2,
    anchor_start: 0,
    anchor_end: 4,
    anchor_quote: "text",
    status,
    merge_message_id: null,
    created_at,
    messages: [],
    points: [],
  };
}

const hueOf = (color: string): number => Number(/^hsl\((\d+) /.exec(color)![1]);

describe("branch colours", () => {
  it("hands out the pool in creation order inside the conversation, not by id", () => {
    const branches = [branch(40, "2026-01-01T10:00:02"), branch(7, "2026-01-01T10:00:03"), branch(91, "2026-01-01T10:00:01")];
    expect(branchColor(branches, 91)).toBe(POOL[0]);
    expect(branchColor(branches, 40)).toBe(POOL[1]);
    expect(branchColor(branches, 7)).toBe(POOL[2]);
    expect(branchNumber(branches, 91)).toBe(1);
    expect(branchNumber(branches, 7)).toBe(3);
  });

  it("breaks created_at ties by id", () => {
    const branches = [branch(5, "2026-01-01"), branch(3, "2026-01-01")];
    expect(branchColor(branches, 3)).toBe(POOL[0]);
    expect(branchColor(branches, 5)).toBe(POOL[1]);
  });

  it("never changes the colour of existing branches when a new one is added", () => {
    const before = [branch(1, "2026-01-01T00:00:01"), branch(2, "2026-01-01T00:00:02")];
    const after = [...before, branch(3, "2026-01-01T00:00:03")];
    expect(branchColor(after, 1)).toBe(branchColor(before, 1));
    expect(branchColor(after, 2)).toBe(branchColor(before, 2));
    expect(branchColor(after, 3)).toBe(POOL[2]);
  });

  it("goes past the pool with golden-angle hues that skip the yellows", () => {
    const branches = Array.from({ length: 30 }, (_, i) => branch(i + 1, `2026-01-01T00:00:${String(i).padStart(2, "0")}`));
    const colors = branchColors(branches);
    expect(colors.get(6)).toBe(POOL[5]);
    expect(colors.get(7)).toBe(generatedColor(6));
    for (let n = 6; n < 30; n++) {
      const color = generatedColor(n);
      expect(color).toMatch(/^hsl\(\d+ 72% 68%\)$/);
      const hue = hueOf(color);
      expect(hue < 40 || hue > 80).toBe(true);
    }
  });

  it("matches the reference generatedColor of devtools/live.html", () => {
    expect(generatedColor(6)).toBe(`hsl(${((6 * 137.508) % 360).toFixed(0)} 72% 68%)`);
    // n = 7: 962.556 % 360 = 242.6, outside the yellow band.
    expect(generatedColor(7)).toBe("hsl(243 72% 68%)");
  });

  it("has no yellow and no light blue in the pool", () => {
    expect(POOL).toEqual(["#FF6FAE", "#4ADE9C", "#FF9F5A", "#A78BFA", "#2DD4BF", "#D9A273"]);
  });
});

describe("anchored passage highlight rules", () => {
  const state: ConversationState = {
    conversation: { id: 1, title: "t", created_at: "2026-01-01" },
    main: [],
    branches: [
      branch(1, "2026-01-01T00:00:01", "open"),
      branch(2, "2026-01-01T00:00:02", "merged"),
      branch(3, "2026-01-01T00:00:03", "discarded"),
    ],
    pending_branch_ids: null,
  };

  it("generates one rule per branch and state in the branch colour", () => {
    const css = highlightRules(state);
    expect(highlightName(1)).toBe("graft-b1");
    expect(highlightName(1, "active")).toBe("graft-b1-active");
    expect(css).toContain(
      `::highlight(graft-b1) { background-color: color-mix(in srgb, ${POOL[0]} 20%, transparent); text-decoration: underline solid ${POOL[0]} 2px; }`,
    );
    expect(css).toContain(`::highlight(graft-b2) { text-decoration: underline solid ${POOL[1]} 2px; }`);
    expect(css).toContain("::highlight(graft-b3) { text-decoration: underline dashed var(--muted) 1px; }");
    expect(css).toContain("::highlight(graft-b3-hover)");
    expect(css).toContain("::highlight(graft-b2-active)");
  });

  it("gives the map's branch lines, nodes and labels the branch colour", () => {
    const layout = layoutConversationMap({
      ...state,
      main: [
        { id: 1, branch_id: null, parent_id: null, role: "user", content: "q", created_at: "x" },
        { id: 2, branch_id: null, parent_id: 1, role: "assistant", content: "text", created_at: "x" },
      ],
    });
    expect(layout.edges.find((e) => e.key === "trunk")?.color).toBeNull();
    expect(layout.edges.find((e) => e.branchId === 2)?.color).toBe(POOL[1]);
    expect(layout.branchLabels.find((b) => b.branchId === 3)?.color).toBe(POOL[2]);
    expect(layout.nodes.find((n) => n.branchId === 1)?.color).toBe(POOL[0]);
  });
});
