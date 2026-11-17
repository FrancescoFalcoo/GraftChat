"""Usage figures in the conversation state: tokens and cost from llm_call_log."""

from api.provider import Completion
from tests.backend.test_app import TAKEAWAY, new_conversation, open_branch, say


def test_a_new_conversation_has_no_usage(client):
    conversation_id = new_conversation(client)
    usage = client.get(f"/api/conversations/{conversation_id}").json()["usage"]
    assert usage["total"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    assert usage["threads"] == [] and usage["messages"] == []


def test_every_answer_carries_the_call_that_produced_it(client, provider, service):
    service.settings.update(spend_cap_usd=1.0)  # these calls cost something
    conversation_id = new_conversation(client)
    provider.queue = [
        Completion("First answer with a passage.", "vendor/chat:free", 120, 30, 0.002),
        Completion("Inside the branch.", "vendor/chat:free", 200, 40, 0.003),
        TAKEAWAY,
    ]
    state = say(client, conversation_id, "hello")
    answer = state["main"][-1]
    branch_id = open_branch(client, conversation_id, answer, "a passage")
    state = say(client, conversation_id, "tell me more", branch_id)
    client.post(f"/api/branches/{branch_id}/takeaway", json={})
    usage = client.get(f"/api/conversations/{conversation_id}").json()["usage"]

    assert usage["total"]["calls"] == 3
    chat = usage["chat"]
    assert (chat["calls"], chat["input_tokens"], chat["output_tokens"]) == (2, 320, 70)
    assert abs(chat["cost"] - 0.005) < 1e-9
    assert usage["takeaway"]["calls"] == 1

    by_message = {m["message_id"]: m for m in usage["messages"]}
    assert by_message[answer["id"]]["input_tokens"] == 120  # the whole context of that answer
    branch_answer = next(b for b in state["branches"] if b["id"] == branch_id)["messages"][-1]
    assert by_message[branch_answer["id"]]["output_tokens"] == 40
    assert len(by_message) == 2  # the take-away produced no message

    threads = {t["branch_id"]: t for t in usage["threads"]}
    assert threads[None]["calls"] == 1
    assert threads[branch_id]["calls"] == 2  # its chat call and its take-away
