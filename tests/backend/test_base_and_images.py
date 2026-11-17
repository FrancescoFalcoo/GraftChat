"""Backend tests for a branch's base (DESIGN.md §14.11) and for images on user messages."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from api import db
from api.provider import ChatMessage, ImagePart, ModelInfo, OpenRouterProvider, fetch_free_models

from .conftest import TEST_MODEL
from .test_app import TAKEAWAY, chat, error_code, merge, new_conversation, open_branch, say  # noqa: F401 (chat is a fixture)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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


# --- images ------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def vision_chat_model(service):
    """The chat model of the tests takes images; "vendor/small:free" does not."""
    models = [ModelInfo(TEST_MODEL, "Chat", 8000, images=True), ModelInfo("vendor/small:free", "Small", None)]
    service._models_fetcher = lambda: models
    service._models = None


def send(client, conversation_id, content="", images=(), branch_id=None):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": content, "branch_id": branch_id, "images": list(images)},
    )


def test_image_is_stored_sent_and_logged_by_reference(client, provider, service):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "what is this?", [{"name": "cat.png", "mime": "image/png", "data": b64(PNG)}])
    assert response.status_code == 200, response.text
    user = response.json()["main"][0]
    (attachment,) = user["attachments"]
    assert (attachment["mime"], attachment["name"], attachment["size"]) == ("image/png", "cat.png", len(PNG))

    (sent,) = provider.calls[-1][1]
    assert sent.content == "what is this?"
    assert [(i.mime, i.data) for i in sent.images] == [("image/png", PNG)]

    with db.connect(service.config.db_path) as conn:
        (log,) = db.list_logs(conn, conversation_id)
    assert json.loads(log.prompt_json) == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": f"attachment:{attachment['id']}"}},
            ],
        }
    ]

    served = client.get(f"/api/attachments/{attachment['id']}")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"


def test_image_only_message_is_allowed_and_names_the_conversation(client, provider):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "", [{"name": "photo.jpg", "data": b64(JPEG)}])
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["conversation"]["title"] == "photo.jpg"
    assert state["main"][0]["attachments"][0]["mime"] == "image/jpeg"  # sniffed, not trusted


def test_images_of_main_reach_a_branch_opened_after_them(client, provider):
    conversation_id = new_conversation(client)
    provider.queue.append("A red square. Nothing else.")
    state = send(client, conversation_id, "describe", [{"name": "a.png", "data": b64(PNG)}]).json()
    branch_id = open_branch(client, conversation_id, state["main"][-1], "red square")
    say(client, conversation_id, "why red?", branch_id)
    first = provider.calls[-1][1][0]
    assert first.role == "user" and len(first.images) == 1


@pytest.mark.parametrize(
    "images, fragment",
    [
        ([{"name": "x.png", "data": "not base64!"}], "base64"),
        ([{"name": "x.txt", "data": b64(b"hello, plain text")}], "not a PNG"),
        ([{"name": "x.png", "data": ""}], "empty"),
        ([{"name": f"{i}.png", "data": b64(PNG)} for i in range(5)], "At most"),
    ],
)
def test_bad_images_are_refused_and_nothing_is_stored(client, provider, images, fragment):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "look", images)
    assert response.status_code == 422 and error_code(response) == "validation"
    assert fragment in response.json()["error"]["message"]
    assert client.get(f"/api/conversations/{conversation_id}").json()["main"] == []
    assert provider.calls == []


def test_a_model_known_not_to_take_images_is_refused_before_storing(client, provider):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "look", [{"name": "a.png", "data": b64(PNG)}])
    assert response.status_code == 200

    client.put("/api/settings", json={"chat_model": "vendor/small:free"})  # listed, text only
    response = send(client, conversation_id, "again", [{"name": "b.png", "data": b64(PNG)}])
    assert response.status_code == 422 and "does not accept images" in response.json()["error"]["message"]
    assert len(client.get(f"/api/conversations/{conversation_id}").json()["main"]) == 2


def test_earlier_images_become_a_note_for_a_text_only_model(client, provider):
    conversation_id = new_conversation(client)
    send(client, conversation_id, "look", [{"name": "a.png", "data": b64(PNG)}])
    client.put("/api/settings", json={"chat_model": "vendor/small:free"})
    say(client, conversation_id, "and now?")
    first = provider.calls[-1][1][0]
    assert first.images == () and "image not sent" in first.content


def test_vision_models_are_flagged(service, client):
    service._models_fetcher = lambda: [ModelInfo(TEST_MODEL, "Chat", 8000, images=True)]
    service._models = None
    assert client.get("/api/models").json()["models"][0]["images"] is True


def test_attachment_not_found(client):
    response = client.get("/api/attachments/999")
    assert response.status_code == 404 and error_code(response) == "not_found"


# --- provider payload ----------------------------------------------------------------------------


def test_openrouter_payload_has_text_and_data_url_parts():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenRouterProvider("k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider.complete("m", [ChatMessage("user", "hi", (ImagePart("image/png", PNG, "attachment:1"),))])
    assert seen[0]["messages"][0]["content"] == [
        {"type": "text", "text": "hi"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64(PNG)}"}},
    ]


def test_model_list_reads_image_input():
    free = {"prompt": "0", "completion": "0"}
    data = [
        {"id": "v/free", "name": "V", "pricing": free, "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
        {"id": "t/free", "name": "T", "pricing": free, "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": data}))
    models = fetch_free_models(httpx.Client(transport=transport))
    assert {m.id: m.images for m in models} == {"t/free": False, "v/free": True}
