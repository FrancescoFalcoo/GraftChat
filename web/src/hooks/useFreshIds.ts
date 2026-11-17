import { useEffect, useRef, useState } from "react";

/** How long an id counts as "just created" (longer than the entrance animations). */
const FRESH_MS = 1200;

/**
 * The ids that appeared while the user was in this conversation (a branch just opened,
 * a merge just applied), for an entrance animation. Ids present when a conversation is
 * loaded are never fresh, so nothing animates on page load or when switching chats.
 */
export function useFreshIds(scope: number | string | null, ids: number[]): ReadonlySet<number> {
  const known = useRef<{ scope: number | string | null; ids: Set<number> }>({ scope: null, ids: new Set() });
  const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set());
  const key = ids.join(",");

  useEffect(() => {
    const current = new Set(ids);
    const prev = known.current;
    known.current = { scope, ids: current };
    if (prev.scope !== scope) {
      setFresh(new Set());
      return;
    }
    const added = ids.filter((id) => !prev.ids.has(id));
    if (added.length === 0) return;
    setFresh((f) => new Set([...f, ...added]));
    // Not cleared on the next change: every id must stop being fresh on its own.
    window.setTimeout(() => {
      setFresh((f) => {
        const next = new Set(f);
        for (const id of added) next.delete(id);
        return next;
      });
    }, FRESH_MS);
  }, [scope, key]);

  return fresh;
}
