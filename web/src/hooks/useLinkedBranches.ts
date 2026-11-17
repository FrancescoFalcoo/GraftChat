import { useEffect } from "react";

/** Class added to every element of the branch under the pointer (box-shadow in var(--c)). */
export const LINKED_CLASS = "branch-linked";

/**
 * Hovering any element tied to a branch (`[data-branch]`) highlights together every
 * element of the same branch: chips, merge node, side panel, merge card, map.
 */
export function useLinkedBranches(): void {
  useEffect(() => {
    let current: string | null = null;
    const clear = (): void => {
      if (current === null) return;
      document.querySelectorAll(`.${LINKED_CLASS}`).forEach((el) => el.classList.remove(LINKED_CLASS));
      current = null;
    };
    const branchOf = (target: EventTarget | null): string | null => {
      const el = target instanceof Element ? target.closest<HTMLElement>("[data-branch]") : null;
      return el?.dataset.branch ?? null;
    };
    const onOver = (e: MouseEvent): void => {
      const id = branchOf(e.target);
      if (id === current) return;
      clear();
      if (id === null || !/^\d+$/.test(id)) return;
      current = id;
      document
        .querySelectorAll(`[data-branch="${id}"]`)
        .forEach((el) => el.classList.add(LINKED_CLASS));
    };
    const onOut = (e: MouseEvent): void => {
      if (branchOf(e.relatedTarget) !== current) clear();
    };
    document.addEventListener("mouseover", onOver);
    document.addEventListener("mouseout", onOut);
    return () => {
      clear();
      document.removeEventListener("mouseover", onOver);
      document.removeEventListener("mouseout", onOut);
    };
  }, []);
}
