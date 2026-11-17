import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { ConversationState, Health, Message, Settings } from "../types";

const NOW = "2026-11-16T10:00:00Z";
const ANSWER = "\u{1F600} First point\n\n**Second** point is here\n- third";

function msg(id: number, role: Message["role"], content: string, branchId: number | null = null): Message {
  return { id, branch_id: branchId, parent_id: null, role, content, created_at: NOW, attachments: [] };
}

function baseState(): ConversationState {
  return {
    conversation: { id: 1, title: "Demo chat", created_at: NOW },
    main: [msg(1, "user", "Tell me things"), msg(2, "assistant", ANSWER)],
    branches: [
      {
        id: 5,
        anchor_message_id: 2,
        anchor_start: 2,
        anchor_end: 13,
        anchor_quote: "First point",
        status: "open",
        merge_message_id: null,
        base_message_id: null,
        created_at: NOW,
        messages: [],
        points: [],
      },
    ],
    pending_branch_ids: null,
  };
}

const SETTINGS: Settings = {
  has_api_key: true,
  api_key_hint: "…a1b2",
  api_key_from_env: false,
  key_info: null,
  spend_cap_usd: 5,
  chat_model: "x/y:free",
  takeaway_model: null,
  month_spend_usd: 1.234,
  fake_llm: true,
};

const HEALTH: Health = { ok: true, core: { "core.tree.thread": true, "core.tree.pending_branches": false } };

type Handler = (body: unknown) => { status?: number; body: unknown };

function serve(routes: Record<string, Handler>, settings: Settings = SETTINGS) {
  const calls: { key: string; body: unknown }[] = [];
  const all: Record<string, Handler> = {
    "GET /api/health": () => ({ body: HEALTH }),
    "GET /api/settings": () => ({ body: settings }),
    "GET /api/models": () => ({ status: 502, body: { error: { code: "provider_error", message: "no list" } } }),
    "GET /api/conversations": () => ({
      body: { conversations: [{ id: 1, title: "Demo chat", created_at: NOW, open_branches: 1 }] },
    }),
    "GET /api/conversations/1": () => ({ body: baseState() }),
    ...routes,
  };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit): Promise<Response> => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ key, body });
    const route = all[key];
    if (!route) return new Response("nope", { status: 404 });
    const res = route(body);
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, bodyOf: (key: string) => calls.find((c) => c.key === key)?.body };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.getSelection()?.removeAllRanges();
  window.localStorage.clear();
});

describe("App", () => {
  it("boots: sidebar, messages, chips, banner, dev notice, fake tag, spend line", async () => {
    serve({});
    render(<App />);
    await screen.findByText("Tell me things");

    const nav = screen.getByRole("navigation", { name: "Conversations" });
    expect(within(nav).getByRole("button", { name: /Demo chat/ }).getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByText("Fake model")).toBeTruthy();
    expect(within(nav).getByText("This month: $1.23 / $5.00")).toBeTruthy();
    expect(
      screen.getByText(
        "Core functions not implemented yet: core.tree.pending_branches. Some features will return errors.",
      ),
    ).toBeTruthy();
    // pending_branch_ids is null: the banner falls back to counting open branches.
    expect(screen.getByText("You came back from 1 branch. Merge?")).toBeTruthy();
    expect(screen.getByRole("button", { name: /«First point»/ })).toBeTruthy();
    expect(document.querySelector("[data-anchor-root]")?.textContent).toBe(ANSWER);
    expect(window.localStorage.getItem("graftchat.lastConversationId")).toBe("1");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens Settings on first load when there is no key", async () => {
    serve({}, { ...SETTINGS, has_api_key: false, api_key_hint: null, fake_llm: false, spend_cap_usd: 0 });
    render(<App />);
    const dialog = await screen.findByRole("dialog", { name: "Settings" });
    expect(within(dialog).getByText(/stored only on this computer and sent only to OpenRouter/)).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Connect OpenRouter" })).toBeTruthy();
    expect(await within(dialog).findByText(/model list could not be loaded/)).toBeTruthy();
    expect(screen.getByText("Free models only")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("says so when it comes back connected from OpenRouter, and cleans the address", async () => {
    window.history.replaceState(null, "", "/?openrouter=connected");
    serve({});
    render(<App />);
    expect(await screen.findByText(/Connected to OpenRouter/)).toBeTruthy();
    expect(window.location.search).toBe("");
  });

  it("opens a branch from a selection with code point offsets", async () => {
    const withBranch = baseState();
    withBranch.branches.push({
      ...withBranch.branches[0],
      id: 6,
      anchor_start: 17,
      anchor_end: 31,
      anchor_quote: "Second** point",
    });
    const server = serve({
      "POST /api/conversations/1/branches": () => ({ status: 201, body: { branch_id: 6, state: withBranch } }),
    });
    render(<App />);
    await screen.findByText("Tell me things");
    const root = document.querySelector<HTMLElement>("[data-anchor-root]")!;

    // Select from "Second" (inside <strong>) to "point" on the same line.
    const strongText = root.querySelector("strong")!.childNodes[1];
    const tail = Array.from(root.querySelectorAll(".ln"))[2].childNodes[1];
    const range = document.createRange();
    range.setStart(strongText, 0);
    range.setEnd(tail, " point".length);
    const sel = document.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    fireEvent.mouseUp(document);

    const button = await screen.findByRole("button", { name: /Open branch/ });
    fireEvent.mouseDown(button);
    fireEvent.click(button);

    const panel = await screen.findByRole("complementary", { name: "Branch" });
    const sent = server.bodyOf("POST /api/conversations/1/branches") as {
      anchor_message_id: number;
      start: number;
      end: number;
      quote: string;
    };
    expect(sent.quote).toBe("Second** point");
    expect(sent.anchor_message_id).toBe(2);
    // The emoji before the selection counts as one code point, not two UTF-16 units.
    expect(Array.from(ANSWER).slice(sent.start, sent.end).join("")).toBe(sent.quote);
    expect(sent.start).toBe(ANSWER.indexOf("Second") - 1);
    // The quote is shown without its markdown markers.
    expect(within(panel).getByText("Second point")).toBeTruthy();
    // Merge… is disabled on an empty branch; the banner hides while the panel is open.
    expect(within(panel).getByRole("button", { name: "Merge…" })).toHaveProperty("disabled", true);
    expect(screen.queryByText(/You came back from/)).toBeNull();

    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.getByText("You came back from 2 branches. Merge?")).toBeTruthy();
  });

  it("ignores selections in user messages", async () => {
    serve({});
    render(<App />);
    const bubble = await screen.findByText("Tell me things");
    const range = document.createRange();
    range.selectNodeContents(bubble);
    document.getSelection()!.addRange(range);
    fireEvent.mouseUp(document);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("button", { name: /Open branch/ })).toBeNull();
  });

  it("sends a message optimistically and shows the reply", async () => {
    const after = baseState();
    after.main.push(msg(3, "user", "More please"), msg(4, "assistant", "Here is more"));
    serve({ "POST /api/conversations/1/messages": () => ({ body: after }) });
    render(<App />);
    await screen.findByText("Tell me things");

    const box = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "More please" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByText("More please")).toBeTruthy();
    expect(screen.getByText("Thinking…")).toBeTruthy();
    expect(box.disabled).toBe(true);

    await screen.findByText("Here is more");
    expect(screen.queryByText("Thinking…")).toBeNull();
    expect(box.value).toBe("");
    expect(box.disabled).toBe(false);
  });

  it("keeps the text when the request is refused before the model call", async () => {
    serve({
      "POST /api/conversations/1/messages": () => ({
        status: 400,
        body: { error: { code: "no_model", message: "Choose a model in the settings." } },
      }),
    });
    render(<App />);
    await screen.findByText("Tell me things");
    const box = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Lost?" } });
    fireEvent.keyDown(box, { key: "Enter" });

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Choose a model in the settings.")).toBeTruthy();
    await waitFor(() => expect(box.value).toBe("Lost?"));
    fireEvent.click(within(alert).getByRole("button", { name: "Open settings" }));
    expect(await screen.findByRole("dialog", { name: "Settings" })).toBeTruthy();
  });

  it("offers Retry and Delete after a provider error", async () => {
    let stored = baseState();
    const dangling = baseState();
    dangling.main.push(msg(3, "user", "Will fail"));
    const answered = structuredClone(dangling);
    answered.main.push(msg(4, "assistant", "Second try worked"));
    const server = serve({
      "GET /api/conversations/1": () => ({ body: stored }),
      "POST /api/conversations/1/messages": () => {
        stored = dangling;
        return { status: 502, body: { error: { code: "provider_error", message: "Provider down." } } };
      },
      "POST /api/conversations/1/generate": () => ({ body: answered }),
      "DELETE /api/messages/3": () => ({ body: baseState() }),
    });
    render(<App />);
    await screen.findByText("Tell me things");
    const box = screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Will fail" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await screen.findByText("Provider down.");
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
    expect(box.value).toBe("");
    expect(box.disabled).toBe(true);

    fireEvent.click(retry);
    await screen.findByText("Second try worked");
    expect(server.bodyOf("POST /api/conversations/1/generate")).toEqual({ branch_id: null });
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(box.disabled).toBe(false);
  });
});
