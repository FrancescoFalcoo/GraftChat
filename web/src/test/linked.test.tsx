import { fireEvent, render, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useFreshIds } from "../hooks/useFreshIds";
import { LINKED_CLASS, useLinkedBranches } from "../hooks/useLinkedBranches";

function Linked() {
  useLinkedBranches();
  return (
    <div>
      <span data-branch="1" data-testid="a">
        <b data-testid="inner">chip</b>
      </span>
      <span data-branch="1" data-testid="b" />
      <span data-branch="2" data-testid="c" />
    </div>
  );
}

describe("linked branch hover", () => {
  it("marks every element of the hovered branch, and only those", () => {
    const { getByTestId } = render(<Linked />);
    fireEvent.mouseOver(getByTestId("inner"));
    expect(getByTestId("a").classList.contains(LINKED_CLASS)).toBe(true);
    expect(getByTestId("b").classList.contains(LINKED_CLASS)).toBe(true);
    expect(getByTestId("c").classList.contains(LINKED_CLASS)).toBe(false);
    fireEvent.mouseOut(getByTestId("inner"), { relatedTarget: document.body });
    expect(getByTestId("a").classList.contains(LINKED_CLASS)).toBe(false);
    expect(getByTestId("b").classList.contains(LINKED_CLASS)).toBe(false);
  });
});

describe("fresh ids", () => {
  it("never marks the ids present when a conversation loads, only the ones added later", () => {
    const { result, rerender } = renderHook(({ scope, ids }) => useFreshIds(scope, ids), {
      initialProps: { scope: null as number | null, ids: [] as number[] },
    });
    rerender({ scope: 1, ids: [1, 2] });
    expect(result.current.size).toBe(0);
    rerender({ scope: 1, ids: [1, 2, 3] });
    expect([...result.current]).toEqual([3]);
    rerender({ scope: 2, ids: [9] });
    expect(result.current.size).toBe(0);
  });
});
