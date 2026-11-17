import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MergeDialog } from "../components/MergeDialog";
import type { MergeFocus } from "../hooks/useGraft";
import type { Branch, ConversationState, Message, Point } from "../types";

const NOW = "2026-11-16T10:00:00Z";

function message(id: number, role: Message["role"], content: string, branchId: number | null): Message {
  return { id, branch_id: branchId, parent_id: null, role, content, created_at: NOW };
}

function branch(id: number, quote: string, messages: Message[]): Branch {
  return {
    id,
    anchor_message_id: 2,
    anchor_start: 0,
    anchor_end: quote.length,
    anchor_quote: quote,
    status: "open",
    merge_message_id: null,
    base_message_id: null,
    created_at: NOW,
    messages,
    points: [],
  };
}

function point(id: number, branchId: number, position: number, title: string, text: string): Point {
  return {
    id,
    branch_id: branchId,
    position,
    title,
    text_generated: text,
    text_final: text,
    included: true,
  };
}

function initialState(): ConversationState {
  return {
    conversation: { id: 1, title: "Test", created_at: NOW },
    main: [message(1, "user", "question", null), message(2, "assistant", "alpha beta gamma", null)],
    branches: [
      branch(1, "alpha", [message(10, "user", "why?", 1), message(11, "assistant", "because", 1)]),
      branch(2, "beta", [message(12, "user", "and?", 2), message(13, "assistant", "so", 2)]),
      branch(3, "gamma", []),
    ],
    pending_branch_ids: [1, 2, 3],
  };
}

interface Call {
  method: string;
  url: string;
  body: unknown;
}

/** A tiny in-memory GraftChat server behind `fetch`. */
function fakeServer() {
  let state = initialState();
  const calls: Call[] = [];
  const failNext = new Map<string, { status: number; code: string; message: string }>();
  let nextPointId = 100;

  const mutate = (fn: (draft: ConversationState) => void): ConversationState => {
    const draft = structuredClone(state);
    fn(draft);
    state = draft;
    return structuredClone(state);
  };
  const ok = (body: unknown): Response =>
    new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

  const handler = async (input: string, init?: RequestInit): Promise<Response> => {
    const method = init?.method ?? "GET";
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, url: input, body });
    const key = `${method} ${input}`;
    const failure = failNext.get(key);
    if (failure) {
      failNext.delete(key);
      return new Response(JSON.stringify({ error: { code: failure.code, message: failure.message } }), {
        status: failure.status,
      });
    }

    let m: RegExpExecArray | null;
    if ((m = /^\/api\/branches\/(\d+)\/takeaway$/.exec(input)) && method === "POST") {
      const id = Number(m[1]);
      return ok(
        mutate((s) => {
          const b = s.branches.find((x) => x.id === id)!;
          b.points = [
            point(nextPointId++, id, 0, `Point A of ${id}`, `Text A of branch ${id}`),
            point(nextPointId++, id, 1, `Point B of ${id}`, `Text B of branch ${id}`),
          ];
        }),
      );
    }
    if ((m = /^\/api\/points\/(\d+)$/.exec(input)) && method === "PATCH") {
      const id = Number(m[1]);
      return ok(
        mutate((s) => {
          for (const b of s.branches) {
            const p = b.points.find((x) => x.id === id);
            if (p) Object.assign(p, body);
          }
        }),
      );
    }
    if ((m = /^\/api\/branches\/(\d+)\/discard$/.exec(input)) && method === "POST") {
      const id = Number(m[1]);
      return ok(
        mutate((s) => {
          s.branches.find((x) => x.id === id)!.status = "discarded";
        }),
      );
    }
    if (input === "/api/conversations/1/merge" && method === "POST") {
      const ids = (body as { branch_ids: number[] }).branch_ids;
      return ok(
        mutate((s) => {
          s.main.push(message(50, "merge", "", null));
          for (const b of s.branches) {
            if (ids.includes(b.id)) {
              b.status = "merged";
              b.merge_message_id = 50;
            }
          }
        }),
      );
    }
    return new Response("not found", { status: 404 });
  };

  return {
    calls,
    failNext,
    fetch: vi.fn(handler),
    callsTo: (part: string) => calls.filter((c) => c.url.includes(part)),
  };
}

function Harness({ focus, onApplied }: { focus: MergeFocus; onApplied: () => void }) {
  const [state, setState] = useState(initialState);
  return (
    <MergeDialog
      state={state}
      focus={focus}
      onState={setState}
      onClose={() => undefined}
      onApplied={onApplied}
      onError={(e) => {
        throw e;
      }}
      onModelCall={() => undefined}
    />
  );
}

function card(quote: string): HTMLElement {
  return screen.getByRole("region", { name: `Branch on: ${quote}` });
}

let server: ReturnType<typeof fakeServer>;

beforeEach(() => {
  server = fakeServer();
  vi.stubGlobal("fetch", server.fetch);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MergeDialog", () => {
  it("generates the take-away only for the branch being merged", async () => {
    render(<Harness focus={[1]} onApplied={() => undefined} />);

    expect(within(card("alpha")).getByRole("radio", { name: "Merge" })).toHaveProperty("checked", true);
    expect(within(card("beta")).getByRole("radio", { name: "Decide later" })).toHaveProperty("checked", true);
    expect(within(card("alpha")).getByText("Generating take-away…")).toBeTruthy();

    await within(card("alpha")).findByText("Point A of 1");
    expect(server.callsTo("/takeaway")).toEqual([
      { method: "POST", url: "/api/branches/1/takeaway", body: {} },
    ]);
    expect(within(card("beta")).queryByText(/Point A/)).toBeNull();
  });

  it("generates take-aways one at a time when a second branch is switched to Merge", async () => {
    render(<Harness focus={[1]} onApplied={() => undefined} />);
    fireEvent.click(within(card("beta")).getByRole("radio", { name: "Merge" }));
    // Branch 1 is still generating: branch 2 waits for its turn.
    expect(server.callsTo("/takeaway").length).toBe(1);
    expect(screen.getByRole("button", { name: "Apply" })).toHaveProperty("disabled", true);

    await within(card("beta")).findByText("Point A of 2");
    expect(server.callsTo("/takeaway").map((c) => c.url)).toEqual([
      "/api/branches/1/takeaway",
      "/api/branches/2/takeaway",
    ]);
  });

  it("does not let an empty branch be merged, even when opened from the banner", async () => {
    render(<Harness focus="all" onApplied={() => undefined} />);
    const empty = card("gamma");
    expect(within(empty).getByRole("radio", { name: "Merge" })).toHaveProperty("disabled", true);
    expect(within(empty).getByRole("radio", { name: "Decide later" })).toHaveProperty("checked", true);
    await within(card("beta")).findByText("Point A of 2");
    expect(server.callsTo("/api/branches/3/")).toEqual([]);
  });

  it("PATCHes a point when its checkbox changes", async () => {
    render(<Harness focus={[1]} onApplied={() => undefined} />);
    const box = (await within(card("alpha")).findByRole("checkbox", {
      name: "Point A of 1",
    })) as HTMLInputElement;
    expect(box.checked).toBe(true);

    fireEvent.click(box);
    await waitFor(() =>
      expect(
        (within(card("alpha")).getByRole("checkbox", { name: "Point A of 1" }) as HTMLInputElement)
          .checked,
      ).toBe(false),
    );
    expect(server.callsTo("/api/points/")).toEqual([
      { method: "PATCH", url: "/api/points/100", body: { included: false } },
    ]);
    expect(within(card("alpha")).getByText(/1 of 2 points/)).toBeTruthy();
  });

  it("saves an edited text on blur and offers to reset it", async () => {
    render(<Harness focus={[1]} onApplied={() => undefined} />);
    const alpha = card("alpha");
    await within(alpha).findByText("Point B of 1");
    fireEvent.click(within(alpha).getByRole("button", { name: /Show the text of “Point B of 1”/ }));
    const area = within(alpha).getByRole("textbox") as HTMLTextAreaElement;
    expect(area.value).toBe("Text B of branch 1");

    fireEvent.change(area, { target: { value: "My own wording" } });
    expect(screen.getByRole("button", { name: "Apply" })).toHaveProperty("disabled", true);
    fireEvent.blur(area);

    await within(alpha).findByText("Edited");
    expect(server.callsTo("/api/points/")).toEqual([
      { method: "PATCH", url: "/api/points/101", body: { text_final: "My own wording" } },
    ]);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Apply" })).toHaveProperty("disabled", false),
    );

    fireEvent.click(within(alpha).getByRole("button", { name: "Reset to generated" }));
    await waitFor(() => expect(within(alpha).queryByText("Edited")).toBeNull());
    expect(server.callsTo("/api/points/")[1].body).toEqual({ text_final: "Text B of branch 1" });
    expect((within(alpha).getByRole("textbox") as HTMLTextAreaElement).value).toBe(
      "Text B of branch 1",
    );
  });

  it("shows a take-away error inline and retries on demand", async () => {
    server.failNext.set("POST /api/branches/1/takeaway", {
      status: 502,
      code: "takeaway_parse",
      message: "The model did not return a usable take-away.",
    });
    render(<Harness focus={[1]} onApplied={() => undefined} />);
    const alpha = card("alpha");
    await within(alpha).findByText("The model did not return a usable take-away.");
    expect(screen.getByRole("button", { name: "Apply" })).toHaveProperty("disabled", true);
    expect(server.callsTo("/takeaway").length).toBe(1);

    fireEvent.click(within(alpha).getByRole("button", { name: "Retry" }));
    await within(alpha).findByText("Point A of 1");
    expect(server.callsTo("/takeaway").length).toBe(2);
  });

  it("regenerates only after a confirmation", async () => {
    render(<Harness focus={[1]} onApplied={() => undefined} />);
    const alpha = card("alpha");
    await within(alpha).findByText("Point A of 1");

    fireEvent.click(within(alpha).getByRole("button", { name: "Regenerate" }));
    const ask = screen.getByRole("dialog", { name: "Regenerate the take-away?" });
    fireEvent.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Regenerate the take-away?" })).toBeNull();
    expect(server.callsTo("/takeaway").length).toBe(1);

    fireEvent.click(within(alpha).getByRole("button", { name: "Regenerate" }));
    const again = screen.getByRole("dialog", { name: "Regenerate the take-away?" });
    fireEvent.click(within(again).getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(server.callsTo("/takeaway").length).toBe(2));
    expect(server.callsTo("/takeaway")[1].body).toEqual({ regenerate: true });
    await within(alpha).findByText("Point A of 1");
  });

  it("Apply discards first, then merges everything in one call", async () => {
    const onApplied = vi.fn();
    render(<Harness focus={[1]} onApplied={onApplied} />);
    fireEvent.click(within(card("beta")).getByRole("radio", { name: "Merge" }));
    fireEvent.click(within(card("gamma")).getByRole("radio", { name: "Discard" }));
    await within(card("beta")).findByText("Point A of 2");

    const apply = screen.getByRole("button", { name: "Apply" });
    await waitFor(() => expect(apply).toHaveProperty("disabled", false));
    server.calls.length = 0;
    fireEvent.click(apply);

    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
    expect(server.calls).toEqual([
      { method: "POST", url: "/api/branches/3/discard", body: undefined },
      { method: "POST", url: "/api/conversations/1/merge", body: { branch_ids: [1, 2] } },
    ]);
  });

  it("Apply with nothing chosen is disabled", async () => {
    render(<Harness focus={[]} onApplied={() => undefined} />);
    expect(screen.getByRole("button", { name: "Apply" })).toHaveProperty("disabled", true);
    expect(server.calls).toEqual([]);
  });
});
