"""Backend tests for a branch's base (DESIGN.md §14.11)."""

from __future__ import annotations

from .test_app import TAKEAWAY, chat, merge, open_branch, say  # noqa: F401 (chat is a fixture)


def summarise_and_merge(client, provider, conversation_id, branch_id):
    provider.queue.append(TAKEAWAY)
    assert client.post(f"/api/branches/{branch_id}/takeaway", json={}).status_code == 200
    response = merge(client, conversation_id, [branch_id])
    assert response.status_code == 200, response.text
    return response.json()


# --- a branch opened after a merge starts from the merged state ----------------------------


def test_second_branch_on_the_same_answer_sees_the_first_merge(client, provider, chat):
    conversation_id, answer = chat
    first = open_branch(client, conversation_id, answer, "First point")
    say(client, conversation_id, "tell me more", first)
    summarise_and_merge(client, provider, conversation_id, first)

    second = open_branch(client, conversation_id, answer, "Third point")
    state = say(client, conversation_id, "and this one?", second)

    sent = provider.calls[-1][1][-1].content
    assert "X was added." in sent and "Y is solved." in sent  # the first branch's take-away
    assert sent.endswith("and this one?")
    node = next(m for m in state["main"] if m["role"] == "merge")
    assert next(b for b in state["branches"] if b["id"] == second)["base_message_id"] == node["id"]


def test_a_branch_does_not_see_merges_made_after_it_was_opened(client, provider, chat):
    conversation_id, answer = chat
    early = open_branch(client, conversation_id, answer, "First point")
    late = open_branch(client, conversation_id, answer, "Third point")
    say(client, conversation_id, "tell me more", early)
    summarise_and_merge(client, provider, conversation_id, early)

    say(client, conversation_id, "and this one?", late)
    sent = " ".join(m.content for m in provider.calls[-1][1])
    assert "X was added." not in sent  # isolation between siblings open at the same time


def test_merge_node_a_branch_started_from_is_not_reused(client, provider, chat):
    conversation_id, answer = chat
    first = open_branch(client, conversation_id, answer, "First point")
    other = open_branch(client, conversation_id, answer, "Second point")
    for branch_id in (first, other):
        say(client, conversation_id, "tell me more", branch_id)
    summarise_and_merge(client, provider, conversation_id, first)

    # opened while main ends on the merge node of `first`
    watcher = open_branch(client, conversation_id, answer, "Third point")
    state = summarise_and_merge(client, provider, conversation_id, other)

    assert [m["role"] for m in state["main"]] == ["user", "assistant", "merge", "merge"]
    by_id = {b["id"]: b for b in state["branches"]}
    assert by_id[first]["merge_message_id"] != by_id[other]["merge_message_id"]

    provider.queue.append("ok")
    say(client, conversation_id, "what do you know?", watcher)
    sent = provider.calls[-1][1][-1].content
    assert sent.count("[merged from branch on:") == 1  # only `first`, merged before it opened


def test_main_after_two_merge_nodes_gets_both_blocks(client, provider, chat):
    conversation_id, answer = chat
    a = open_branch(client, conversation_id, answer, "First point")
    b = open_branch(client, conversation_id, answer, "Second point")
    for branch_id in (a, b):
        say(client, conversation_id, "tell me more", branch_id)
    summarise_and_merge(client, provider, conversation_id, a)
    open_branch(client, conversation_id, answer, "Third point")
    summarise_and_merge(client, provider, conversation_id, b)

    say(client, conversation_id, "back on main")
    assert provider.calls[-1][1][-1].content.count("[merged from branch on:") == 2
