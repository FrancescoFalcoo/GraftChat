"""End-to-end tests of the HTTP API (docs/API.md) against a scripted provider.

``core`` is the real one: these tests also check that the API hands the model
exactly the context ``core.context`` builds.
"""

from __future__ import annotations

import json

import pytest

from api import db
from api.provider import ProviderError
from core import context, tree
from core.tree import InvariantError

from .conftest import TEST_KEY, TEST_MODEL

TAKEAWAY = json.dumps(
    [
        {"title": "added X", "text": "X was added."},
        {"title": "solved Y", "text": "Y is solved."},
    ]
)


def error_code(response):
    return response.json()["error"]["code"]


def new_conversation(client) -> int:
    response = client.post("/api/conversations", json={})
    assert response.status_code == 201
    return response.json()["conversation"]["id"]


def say(client, conversation_id, content, branch_id=None):
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": content, "branch_id": branch_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def open_branch(client, conversation_id, anchor, quote):
    start = anchor["content"].index(quote)
    response = client.post(
        f"/api/conversations/{conversation_id}/branches",
        json={
            "anchor_message_id": anchor["id"],
            "start": start,
            "end": start + len(quote),
            "quote": quote,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["branch_id"]


@pytest.fixture
def chat(client, provider):
    """A conversation with one exchange on main. Returns (conversation_id, assistant message)."""
    conversation_id = new_conversation(client)
    provider.queue.append("First point. Second point 🌱 here. Third point.")
    state = say(client, conversation_id, "Explain three things")
    return conversation_id, state["main"][-1]


# --- health, settings, models ---------------------------------------------------------


def test_health_reports_core_functions(client, monkeypatch):
    def stub(branches):
        raise NotImplementedError

    monkeypatch.setattr(tree, "pending_branches", stub)
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["core"]["core.tree.pending_branches"] is False
    assert body["core"]["core.context.build_main_context"] is True


def test_settings_never_return_the_key(client):
    body = client.get("/api/settings").json()
    assert body == {
        "has_api_key": True,
        "api_key_hint": "…0001",
        "api_key_from_env": False,
        "key_info": None,
        "spend_cap_usd": 0.0,
        "chat_model": TEST_MODEL,
        "takeaway_model": None,
        "month_spend_usd": 0.0,
        "fake_llm": False,
    }
    assert TEST_KEY not in client.get("/api/settings").text


def test_settings_update_is_partial(client):
    body = client.put("/api/settings", json={"spend_cap_usd": 3, "takeaway_model": " small "}).json()
    assert (body["spend_cap_usd"], body["takeaway_model"], body["chat_model"]) == (3.0, "small", TEST_MODEL)
    body = client.put("/api/settings", json={"takeaway_model": None}).json()
    assert body["takeaway_model"] is None and body["spend_cap_usd"] == 3.0
    assert body["has_api_key"] is True


@pytest.mark.parametrize(
    "payload",
    [{"api_key": "  "}, {"spend_cap_usd": -1}, {"spend_cap_usd": None}, {"unknown_field": 1}],
)
def test_settings_reject_bad_values(client, payload):
    response = client.put("/api/settings", json=payload)
    assert response.status_code == 422 and error_code(response) == "validation"


def test_api_key_can_be_removed(client):
    body = client.delete("/api/settings/api-key").json()
    assert (body["has_api_key"], body["api_key_hint"]) == (False, None)


def test_models_endpoint(client):
    models = client.get("/api/models").json()["models"]
    assert models[0] == {"id": "vendor/chat:free", "name": "Chat", "context_length": 8000, "images": False}


def test_unknown_endpoint_uses_the_error_shape(client):
    response = client.get("/api/nope")
    assert response.status_code == 404 and error_code(response) == "not_found"


# --- conversations and chat -------------------------------------------------------------


def test_new_conversation_is_empty(client):
    state = client.post("/api/conversations", json={}).json()
    assert state["conversation"]["title"] == "New chat"
    assert (state["main"], state["branches"], state["pending_branch_ids"]) == ([], [], [])


def test_chat_stores_both_messages_logs_the_call_and_names_the_conversation(client, provider, service):
    conversation_id = new_conversation(client)
    provider.queue.append("Hello human")
    state = say(client, conversation_id, "  Hi there\nsecond line  ")

    user, assistant = state["main"]
    assert (user["role"], user["content"], user["parent_id"]) == ("user", "Hi there\nsecond line", None)
    assert (assistant["role"], assistant["content"], assistant["parent_id"]) == (
        "assistant",
        "Hello human",
        user["id"],
    )
    assert state["conversation"]["title"] == "Hi there"

    model, prompt, tag = provider.calls[0]
    assert (model, tag) == (TEST_MODEL, "chat")
    assert [(m.role, m.content) for m in prompt] == [("user", "Hi there\nsecond line")]
    assert provider.keys == [TEST_KEY]

    with service._connect() as conn:
        (entry,) = db.list_logs(conn, conversation_id)
    assert (entry.purpose.value, entry.branch_id, entry.model) == ("chat", None, TEST_MODEL)
    assert (entry.input_tokens, entry.output_tokens, entry.response_text) == (10, 5, "Hello human")
    assert json.loads(entry.prompt_json) == [{"role": "user", "content": "Hi there\nsecond line"}]
    assert TEST_KEY not in entry.prompt_json


def test_second_message_continues_the_chain_and_sends_history(client, provider, chat):
    conversation_id, first_answer = chat
    state = say(client, conversation_id, "And then?")
    assert [m["role"] for m in state["main"]] == ["user", "assistant", "user", "assistant"]
    assert state["main"][2]["parent_id"] == first_answer["id"]
    assert [m.role for m in provider.calls[-1][1]] == ["user", "assistant", "user"]


def test_long_first_message_gives_a_truncated_title(client):
    conversation_id = new_conversation(client)
    state = say(client, conversation_id, "word " * 40)
    title = state["conversation"]["title"]
    assert len(title) <= 60 and title.endswith("…")


def test_conversation_list_and_rename(client, chat):
    conversation_id, _ = chat
    other = new_conversation(client)
    listed = client.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [other, conversation_id]
    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": " Mine "}).json()
    assert renamed["conversation"]["title"] == "Mine"
    assert client.patch(f"/api/conversations/{conversation_id}", json={"title": " "}).status_code == 422


@pytest.mark.parametrize("content", ["", "   \n "])
def test_blank_message_is_rejected(client, chat, content):
    conversation_id, _ = chat
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": content})
    assert response.status_code == 422 and error_code(response) == "validation"


def test_missing_things_are_404(client, chat):
    conversation_id, _ = chat
    assert client.get("/api/conversations/999").status_code == 404
    assert client.post("/api/conversations/999/messages", json={"content": "x"}).status_code == 404
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "x", "branch_id": 999}
    )
    assert response.status_code == 404
    assert client.post("/api/branches/999/discard").status_code == 404
    assert client.patch("/api/points/999", json={"included": False}).status_code == 404
    assert client.delete("/api/messages/999").status_code == 404


# --- refusals before the model call: nothing is stored ---------------------------------------


def unchanged(client, conversation_id, expected_main_length):
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert len(state["main"]) == expected_main_length


def test_no_api_key(client, provider, chat):
    conversation_id, _ = chat
    client.delete("/api/settings/api-key")
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    assert response.status_code == 400 and error_code(response) == "no_api_key"
    unchanged(client, conversation_id, 2)
    assert len(provider.calls) == 1


def test_key_from_environment_is_used(client, provider, chat, monkeypatch):
    conversation_id, _ = chat
    client.delete("/api/settings/api-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env-123456")
    say(client, conversation_id, "x")
    assert provider.keys[-1] == "sk-from-env-123456"
    assert client.get("/api/settings").json()["api_key_from_env"] is True


def test_no_model(client, chat):
    conversation_id, _ = chat
    client.put("/api/settings", json={"chat_model": None})
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    assert response.status_code == 400 and error_code(response) == "no_model"
    unchanged(client, conversation_id, 2)


def test_cap_zero_allows_free_calls_and_blocks_after_any_cost(client, provider, chat):
    conversation_id, _ = chat  # one free call already made, cap is 0
    provider.cost = 0.002
    say(client, conversation_id, "this one costs")  # allowed: nothing spent so far
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    assert response.status_code == 402 and error_code(response) == "spend_cap_reached"
    unchanged(client, conversation_id, 4)
    assert client.get("/api/settings").json()["month_spend_usd"] == pytest.approx(0.002)


def test_positive_cap_blocks_when_reached(client, provider, chat):
    conversation_id, _ = chat
    client.put("/api/settings", json={"spend_cap_usd": 0.01})
    provider.cost = 0.006
    say(client, conversation_id, "one")
    say(client, conversation_id, "two")  # 0.006 < 0.01: allowed, brings the total to 0.012
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "three"})
    assert error_code(response) == "spend_cap_reached"
    assert len(provider.calls) == 3


def test_core_stub_is_reported_as_501_and_nothing_is_stored(client, provider, chat, monkeypatch):
    conversation_id, _ = chat

    def build_main_context(messages, branches, points):
        raise NotImplementedError

    monkeypatch.setattr(context, "build_main_context", build_main_context)
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    assert response.status_code == 501 and error_code(response) == "core_not_implemented"
    assert "build_main_context" in response.json()["error"]["message"]
    unchanged(client, conversation_id, 2)
    assert len(provider.calls) == 1


def test_state_works_while_pending_branches_is_a_stub(client, chat, monkeypatch):
    conversation_id, _ = chat

    def stub(branches):
        raise NotImplementedError

    monkeypatch.setattr(tree, "pending_branches", stub)
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert state["pending_branch_ids"] is None and len(state["main"]) == 2


def test_failed_whole_state_check_rolls_the_change_back(client, chat, monkeypatch):
    conversation_id, _ = chat

    def check_invariants(messages, branches, points):
        raise InvariantError("made-up violation")

    monkeypatch.setattr(tree, "check_invariants", check_invariants)
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    assert response.status_code == 409 and error_code(response) == "invariant"
    assert "made-up violation" in response.json()["error"]["message"]
    unchanged(client, conversation_id, 2)


# --- provider failures: the user message stays, retry or delete -------------------------------


@pytest.mark.parametrize(
    ("kind", "code"),
    [("auth", "provider_auth"), ("rate_limit", "provider_rate_limit"), ("error", "provider_error")],
)
def test_provider_failure_keeps_the_user_message(client, provider, chat, kind, code):
    conversation_id, _ = chat
    provider.queue.append(ProviderError(kind, "it broke"))
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "again"})
    assert response.status_code == 502 and error_code(response) == code
    assert response.json()["error"]["message"] == "it broke"

    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert [m["role"] for m in state["main"]] == ["user", "assistant", "user"]

    # the thread is now waiting for a reply: no new message
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "more"})
    assert response.status_code == 409 and error_code(response) == "conflict"


def test_retry_generates_the_missing_reply(client, provider, chat):
    conversation_id, _ = chat
    provider.queue.append(ProviderError("error", "it broke"))
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "again"})

    provider.queue.append("second answer")
    response = client.post(f"/api/conversations/{conversation_id}/generate", json={})
    assert response.status_code == 200
    main = response.json()["main"]
    assert [m["content"] for m in main[-2:]] == ["again", "second answer"]
    assert main[-1]["parent_id"] == main[-2]["id"]


def test_generate_needs_a_thread_waiting_for_a_reply(client, chat):
    conversation_id, _ = chat
    response = client.post(f"/api/conversations/{conversation_id}/generate", json={})
    assert response.status_code == 409 and error_code(response) == "conflict"


def test_dangling_user_message_can_be_deleted_but_nothing_else(client, provider, chat):
    conversation_id, answer = chat
    provider.queue.append(ProviderError("error", "it broke"))
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "again"})
    main = client.get(f"/api/conversations/{conversation_id}").json()["main"]

    assert client.delete(f"/api/messages/{answer['id']}").status_code == 409  # an assistant message
    assert client.delete(f"/api/messages/{main[0]['id']}").status_code == 409  # has a reply

    response = client.delete(f"/api/messages/{main[-1]['id']}")
    assert response.status_code == 200
    assert [m["role"] for m in response.json()["main"]] == ["user", "assistant"]
    say(client, conversation_id, "fresh start")  # the thread accepts messages again


# --- branches --------------------------------------------------------------------------------


def test_open_branch_uses_code_point_offsets(client, chat):
    conversation_id, answer = chat
    quote = "🌱 here"
    start = answer["content"].index(quote)  # Python offsets = code points
    response = client.post(
        f"/api/conversations/{conversation_id}/branches",
        json={"anchor_message_id": answer["id"], "start": start, "end": start + len(quote), "quote": quote},
    )
    assert response.status_code == 201
    body = response.json()
    (branch,) = body["state"]["branches"]
    assert branch["id"] == body["branch_id"]
    assert (branch["anchor_quote"], branch["status"], branch["merge_message_id"]) == (quote, "open", None)
    assert (branch["messages"], branch["points"]) == ([], [])
    assert body["state"]["pending_branch_ids"] == [branch["id"]]
    assert client.get("/api/conversations").json()["conversations"][0]["open_branches"] == 1


def test_open_branch_rejects_a_quote_that_does_not_match(client, chat):
    conversation_id, answer = chat
    # what a frontend sending UTF-16 offsets would do for text after the emoji
    quote = "Third"
    start = answer["content"].index(quote) + 1
    response = client.post(
        f"/api/conversations/{conversation_id}/branches",
        json={"anchor_message_id": answer["id"], "start": start, "end": start + len(quote), "quote": quote},
    )
    assert response.status_code == 422 and error_code(response) == "validation"


def test_open_branch_rules_come_from_core(client, chat):
    conversation_id, answer = chat
    user = client.get(f"/api/conversations/{conversation_id}").json()["main"][0]
    cases = [
        {"anchor_message_id": user["id"], "start": 0, "end": 3, "quote": user["content"][:3]},
        {"anchor_message_id": answer["id"], "start": 5, "end": 5, "quote": ""},
        {"anchor_message_id": answer["id"], "start": 0, "end": 10_000, "quote": "x"},
    ]
    for payload in cases:
        response = client.post(f"/api/conversations/{conversation_id}/branches", json=payload)
        assert response.status_code == 409 and error_code(response) == "invariant", payload
    other = new_conversation(client)
    response = client.post(
        f"/api/conversations/{other}/branches",
        json={"anchor_message_id": answer["id"], "start": 0, "end": 5, "quote": "First"},
    )
    assert response.status_code == 404  # the anchor belongs to another conversation


def test_branch_chat_is_its_own_thread_and_gets_the_branch_context(client, provider, chat):
    conversation_id, answer = chat
    branch_id = open_branch(client, conversation_id, answer, "Second point")
    provider.queue += ["because A", "and B"]
    say(client, conversation_id, "why?", branch_id)
    state = say(client, conversation_id, "more?", branch_id)

    (branch,) = state["branches"]
    assert [(m["role"], m["content"]) for m in branch["messages"]] == [
        ("user", "why?"),
        ("assistant", "because A"),
        ("user", "more?"),
        ("assistant", "and B"),
    ]
    assert branch["messages"][0]["parent_id"] is None  # DESIGN §14.1
    assert all(m["branch_id"] == branch_id for m in branch["messages"])
    assert len(state["main"]) == 2  # main untouched
    assert state["conversation"]["title"] == "Explain three things"

    # DESIGN §7: main up to the anchor, the anchor note on the branch's first
    # user message, then the branch's own messages
    prompt = provider.calls[-1][1]
    assert [m.role for m in prompt] == ["user", "assistant", "user", "assistant", "user"]
    assert prompt[1].content == answer["content"]
    note = context.render_anchor_note("Second point")
    assert prompt[2].content == "\n".join([context.BLOCK_START, note, context.BLOCK_END, "", "why?"])
    assert prompt[-1].content == "more?"


def test_sibling_branches_do_not_see_each_other(client, provider, chat):
    conversation_id, answer = chat
    first = open_branch(client, conversation_id, answer, "First point")
    second = open_branch(client, conversation_id, answer, "Third point")
    say(client, conversation_id, "secret of the first branch", first)
    say(client, conversation_id, "question in the second", second)
    sent = " ".join(m.content for m in provider.calls[-1][1])
    assert "secret of the first branch" not in sent


def test_discard(client, chat):
    conversation_id, answer = chat
    branch_id = open_branch(client, conversation_id, answer, "First point")  # empty branch
    state = client.post(f"/api/branches/{branch_id}/discard").json()
    assert state["branches"][0]["status"] == "discarded"
    assert state["pending_branch_ids"] == []

    again = client.post(f"/api/branches/{branch_id}/discard")
    assert again.status_code == 409 and error_code(again) == "invariant"
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "x", "branch_id": branch_id}
    )
    assert response.status_code == 409 and error_code(response) == "conflict"


# --- take-away -------------------------------------------------------------------------------


@pytest.fixture
def branch(client, provider, chat):
    """An open branch with one exchange. Returns (conversation_id, branch_id)."""
    conversation_id, answer = chat
    branch_id = open_branch(client, conversation_id, answer, "Second point")
    provider.queue.append("because A")
    say(client, conversation_id, "why?", branch_id)
    return conversation_id, branch_id


def points_of(state, branch_id):
    return next(b for b in state["branches"] if b["id"] == branch_id)["points"]


def test_takeaway_is_generated_once_and_cached(client, provider, service, branch):
    conversation_id, branch_id = branch
    client.put("/api/settings", json={"takeaway_model": "vendor/small:free"})
    provider.queue.append(TAKEAWAY)
    state = client.post(f"/api/branches/{branch_id}/takeaway", json={}).json()

    points = points_of(state, branch_id)
    assert [(p["position"], p["title"], p["text_generated"], p["text_final"], p["included"]) for p in points] == [
        (0, "added X", "X was added.", "X was added.", True),
        (1, "solved Y", "Y is solved.", "Y is solved.", True),
    ]
    model, prompt, tag = provider.calls[-1]
    assert (model, tag) == ("vendor/small:free", "takeaway")
    assert "«Second point»" in prompt[-1].content and "because A" in prompt[-1].content

    calls = len(provider.calls)
    again = client.post(f"/api/branches/{branch_id}/takeaway", json={}).json()
    assert points_of(again, branch_id) == points
    assert len(provider.calls) == calls  # cached: no second call

    with service._connect() as conn:
        entry = db.list_logs(conn, conversation_id)[-1]
    assert (entry.purpose.value, entry.branch_id, entry.response_text) == ("takeaway", branch_id, TAKEAWAY)


def test_takeaway_falls_back_to_the_chat_model(client, provider, branch):
    _, branch_id = branch
    provider.queue.append(TAKEAWAY)
    client.post(f"/api/branches/{branch_id}/takeaway", json={})
    assert provider.calls[-1][0] == TEST_MODEL


def test_takeaway_retries_once_on_an_unreadable_answer(client, provider, service, branch):
    conversation_id, branch_id = branch
    provider.queue += ["Sure, here is a summary!", TAKEAWAY]
    response = client.post(f"/api/branches/{branch_id}/takeaway", json={})
    assert response.status_code == 200 and len(points_of(response.json(), branch_id)) == 2

    retry_prompt = provider.calls[-1][1]
    assert retry_prompt[-2].content == "Sure, here is a summary!"
    with service._connect() as conn:
        assert [e.purpose.value for e in db.list_logs(conn, conversation_id)][-2:] == ["takeaway"] * 2


def test_takeaway_gives_up_after_two_unreadable_answers(client, provider, branch):
    _, branch_id = branch
    provider.queue += ["nope", "still nope"]
    response = client.post(f"/api/branches/{branch_id}/takeaway", json={})
    assert response.status_code == 502 and error_code(response) == "takeaway_parse"
    state = client.get(f"/api/conversations/{branch[0]}").json()
    assert points_of(state, branch_id) == []


def test_regenerate_replaces_the_points_only_on_request(client, provider, branch):
    _, branch_id = branch
    provider.queue.append(TAKEAWAY)
    client.post(f"/api/branches/{branch_id}/takeaway", json={})
    provider.queue.append(json.dumps([{"title": "new", "text": "New point."}]))
    state = client.post(f"/api/branches/{branch_id}/takeaway", json={"regenerate": True}).json()
    assert [p["text_generated"] for p in points_of(state, branch_id)] == ["New point."]


def test_takeaway_refuses_empty_and_closed_branches(client, provider, chat):
    conversation_id, answer = chat
    empty = open_branch(client, conversation_id, answer, "First point")
    response = client.post(f"/api/branches/{empty}/takeaway", json={})
    assert response.status_code == 409 and error_code(response) == "conflict"
    client.post(f"/api/branches/{empty}/discard")
    response = client.post(f"/api/branches/{empty}/takeaway", json={})
    assert response.status_code == 409 and error_code(response) == "conflict"
    assert len(provider.calls) == 1  # only the chat fixture's call


def test_takeaway_respects_the_spend_cap(client, provider, branch):
    _, branch_id = branch
    provider.cost = 0.01
    conversation_id = branch[0]
    say(client, conversation_id, "costly", branch_id)
    response = client.post(f"/api/branches/{branch_id}/takeaway", json={})
    assert response.status_code == 402 and error_code(response) == "spend_cap_reached"


# --- points -----------------------------------------------------------------------------------


@pytest.fixture
def summarised(client, provider, branch):
    """An open branch with a generated take-away. Returns (conversation_id, branch_id, points)."""
    conversation_id, branch_id = branch
    provider.queue.append(TAKEAWAY)
    state = client.post(f"/api/branches/{branch_id}/takeaway", json={}).json()
    return conversation_id, branch_id, points_of(state, branch_id)


def test_point_checkbox_and_text_can_change_generated_text_cannot(client, summarised):
    _, branch_id, (first, second) = summarised
    state = client.patch(f"/api/points/{first['id']}", json={"included": False}).json()
    state = client.patch(f"/api/points/{second['id']}", json={"text_final": "My own words."}).json()

    first, second = points_of(state, branch_id)
    assert (first["included"], first["text_final"]) == (False, "X was added.")
    assert (second["included"], second["text_final"], second["text_generated"]) == (
        True,
        "My own words.",
        "Y is solved.",
    )


@pytest.mark.parametrize("payload", [{}, {"text_final": "  "}, {"text_generated": "hack"}])
def test_point_update_validation(client, summarised, payload):
    _, _, (first, _) = summarised
    response = client.patch(f"/api/points/{first['id']}", json=payload)
    assert response.status_code == 422 and error_code(response) == "validation"


# --- merge ------------------------------------------------------------------------------------


def merge(client, conversation_id, branch_ids):
    return client.post(f"/api/conversations/{conversation_id}/merge", json={"branch_ids": branch_ids})


def test_merge_appends_a_merge_node_and_closes_the_branch(client, provider, summarised):
    conversation_id, branch_id, points = summarised
    client.patch(f"/api/points/{points[0]['id']}", json={"included": False})

    response = merge(client, conversation_id, [branch_id])
    assert response.status_code == 200, response.text
    state = response.json()

    node = state["main"][-1]
    assert (node["role"], node["content"], node["branch_id"]) == ("merge", "", None)
    assert node["parent_id"] == state["main"][-2]["id"]
    (merged,) = state["branches"]
    assert (merged["status"], merged["merge_message_id"]) == ("merged", node["id"])
    assert [p["included"] for p in merged["points"]] == [False, True]
    assert state["pending_branch_ids"] == []

    # main goes on after the merge node
    state = say(client, conversation_id, "back on main")
    assert [m["role"] for m in state["main"]] == ["user", "assistant", "merge", "user", "assistant"]
    assert state["main"][3]["parent_id"] == node["id"]

    # the model receives only the ticked point, in front of what the user typed (DESIGN §7);
    # the stored message stays exactly what the user typed
    sent = provider.calls[-1][1][-1].content
    header = context.MERGE_HEADER.format(anchor_quote="Second point")
    assert sent == "\n".join(
        [context.BLOCK_START, header, "- Y is solved.", context.BLOCK_END, "", "back on main"]
    )
    assert "X was added." not in " ".join(m.content for m in provider.calls[-1][1])
    assert state["main"][3]["content"] == "back on main"


def test_merged_branch_is_frozen(client, summarised):
    conversation_id, branch_id, points = summarised
    merge(client, conversation_id, [branch_id])

    for response in (
        client.patch(f"/api/points/{points[0]['id']}", json={"included": False}),
        client.post(f"/api/branches/{branch_id}/takeaway", json={"regenerate": True}),
        client.post(
            f"/api/conversations/{conversation_id}/messages", json={"content": "x", "branch_id": branch_id}
        ),
    ):
        assert response.status_code == 409 and error_code(response) == "conflict"
    for response in (merge(client, conversation_id, [branch_id]), client.post(f"/api/branches/{branch_id}/discard")):
        assert response.status_code == 409 and error_code(response) == "invariant"  # DESIGN §14.5


def test_two_branches_merged_together_share_one_node(client, provider, chat):
    conversation_id, answer = chat
    ids = []
    for quote in ("First point", "Third point"):
        branch_id = open_branch(client, conversation_id, answer, quote)
        say(client, conversation_id, "tell me more", branch_id)
        provider.queue.append(TAKEAWAY)
        client.post(f"/api/branches/{branch_id}/takeaway", json={})
        ids.append(branch_id)

    state = merge(client, conversation_id, ids).json()
    nodes = [m for m in state["main"] if m["role"] == "merge"]
    assert len(nodes) == 1
    assert {b["merge_message_id"] for b in state["branches"]} == {nodes[0]["id"]}


def test_merging_again_before_main_continues_reuses_the_node(client, provider, chat):
    conversation_id, answer = chat
    ids = []
    for quote in ("First point", "Third point"):
        branch_id = open_branch(client, conversation_id, answer, quote)
        say(client, conversation_id, "tell me more", branch_id)
        provider.queue.append(TAKEAWAY)
        client.post(f"/api/branches/{branch_id}/takeaway", json={})
        ids.append(branch_id)

    merge(client, conversation_id, [ids[0]])
    state = merge(client, conversation_id, [ids[1]]).json()
    assert [m["role"] for m in state["main"]] == ["user", "assistant", "merge"]
    assert len({b["merge_message_id"] for b in state["branches"]}) == 1


def test_merge_with_no_checked_point_is_valid(client, provider, summarised):
    conversation_id, branch_id, points = summarised
    for point in points:
        client.patch(f"/api/points/{point['id']}", json={"included": False})
    state = merge(client, conversation_id, [branch_id]).json()
    assert state["branches"][0]["status"] == "merged"  # DESIGN §14.4
    say(client, conversation_id, "back on main")
    assert provider.calls[-1][1][-1].content == "back on main"  # nothing injected


def test_merge_refusals_change_nothing(client, provider, chat):
    conversation_id, answer = chat
    empty = open_branch(client, conversation_id, answer, "First point")
    unsummarised = open_branch(client, conversation_id, answer, "Third point")
    say(client, conversation_id, "tell me more", unsummarised)

    assert error_code(merge(client, conversation_id, [])) == "validation"
    assert error_code(merge(client, conversation_id, [unsummarised, unsummarised])) == "validation"
    assert merge(client, conversation_id, [999]).status_code == 404
    assert error_code(merge(client, conversation_id, [unsummarised])) == "conflict"  # no take-away yet
    assert error_code(merge(client, conversation_id, [empty])) == "invariant"  # DESIGN §14.2, from core

    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert [m["role"] for m in state["main"]] == ["user", "assistant"]  # no stray merge node
    assert {b["status"] for b in state["branches"]} == {"open"}


def test_merge_is_all_or_nothing(client, provider, summarised):
    conversation_id, branch_id, _ = summarised
    answer = client.get(f"/api/conversations/{conversation_id}").json()["main"][1]
    empty = open_branch(client, conversation_id, answer, "First point")

    response = merge(client, conversation_id, [branch_id, empty])
    assert response.status_code == 409
    state = client.get(f"/api/conversations/{conversation_id}").json()
    assert {b["status"] for b in state["branches"]} == {"open"}
    assert state["main"][-1]["role"] == "assistant"


def test_merge_waits_for_a_pending_reply_on_main(client, provider, summarised):
    conversation_id, branch_id, _ = summarised
    provider.queue.append(ProviderError("error", "down"))
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "unanswered"})
    response = merge(client, conversation_id, [branch_id])
    assert response.status_code == 409 and error_code(response) == "conflict"


# --- the frontend ------------------------------------------------------------------------------


def test_without_a_built_frontend_the_root_page_says_how_to_build_it(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "npm run build" in response.text


def test_built_frontend_is_served_next_to_the_api(config, service, tmp_path):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from api.app import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>built app</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")

    with_frontend = TestClient(create_app(service, replace(config, web_dist=dist)), base_url="http://127.0.0.1")
    assert "built app" in with_frontend.get("/").text
    assert with_frontend.get("/assets/app.js").status_code == 200
    assert with_frontend.get("/api/health").json()["ok"] is True
    missing = with_frontend.get("/api/nope")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
