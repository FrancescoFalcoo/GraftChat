import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, toApiError } from "../api";

function stubFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const mock = vi.fn(impl);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function caught(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    return e as ApiError;
  }
  throw new Error("expected the call to throw");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("builds ApiError from the {error:{code,message}} body", async () => {
    stubFetch(async () =>
      json(402, { error: { code: "spend_cap_reached", message: "Monthly cap reached." } }),
    );
    const err = await caught(api.sendMessage(1, "hi", null));
    expect(err.status).toBe(402);
    expect(err.code).toBe("spend_cap_reached");
    expect(err.message).toBe("Monthly cap reached.");
  });

  it("keeps the server message of core_not_implemented", async () => {
    stubFetch(async () =>
      json(501, {
        error: { code: "core_not_implemented", message: "core.tree.pending_branches is a stub" },
      }),
    );
    const err = await caught(api.getConversation(3));
    expect(err).toMatchObject({
      status: 501,
      code: "core_not_implemented",
      message: "core.tree.pending_branches is a stub",
    });
  });

  it("falls back to a generic error when the body is not JSON", async () => {
    stubFetch(async () => new Response("<html>Bad gateway</html>", { status: 502 }));
    const err = await caught(api.health());
    expect(err.status).toBe(502);
    expect(err.code).toBe("http_error");
    expect(err.message).toContain("502");
  });

  it("falls back to a generic error when the JSON has another shape", async () => {
    stubFetch(async () => json(500, { error: "boom" }));
    expect((await caught(api.health())).code).toBe("http_error");
    stubFetch(async () => json(422, { detail: "Field required" }));
    const err = await caught(api.health());
    expect(err).toMatchObject({ status: 422, code: "http_error", message: "Field required" });
  });

  it("reports network failures with status 0", async () => {
    stubFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const err = await caught(api.listConversations());
    expect(err.status).toBe(0);
    expect(err.code).toBe("network");
  });

  it("rejects a successful response that is not JSON", async () => {
    stubFetch(async () => new Response("ok", { status: 200 }));
    expect((await caught(api.getSettings())).code).toBe("bad_response");
  });

  it("sends JSON bodies with the right method and path", async () => {
    const mock = stubFetch(async () => json(200, { branch_id: 7, state: {} }));
    await api.openBranch(4, { anchor_message_id: 9, start: 2, end: 5, quote: "abc" });
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/conversations/4/branches");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      anchor_message_id: 9,
      start: 2,
      end: 5,
      quote: "abc",
    });
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("sends no body on GET and unwraps list responses", async () => {
    const mock = stubFetch(async () => json(200, { conversations: [{ id: 1 }] }));
    const list = await api.listConversations();
    expect(list).toEqual([{ id: 1 }]);
    expect(mock.mock.calls[0][1]?.body).toBeUndefined();
  });

  it("toApiError wraps unknown errors", () => {
    const e = new ApiError(409, "conflict", "x");
    expect(toApiError(e)).toBe(e);
    expect(toApiError(new Error("boom"))).toMatchObject({ status: 0, code: "unknown" });
    expect(toApiError("nope").message).toBe("Unexpected error.");
  });
});
