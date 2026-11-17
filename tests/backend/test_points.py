"""Take-away points the user adds by hand (DESIGN.md §14.14)."""

from __future__ import annotations

import pytest

from core import context

from .test_app import (  # noqa: F401 (fixtures)
    TAKEAWAY,
    branch,
    chat,
    error_code,
    merge,
    open_branch,
    points_of,
    say,
    summarised,
)


def add(client, branch_id, text, title=None):
    body = {"text": text} if title is None else {"text": text, "title": title}
    return client.post(f"/api/branches/{branch_id}/points", json=body)


def test_added_point_is_included_marked_and_enters_the_context(client, provider, summarised):
    conversation_id, branch_id, _ = summarised
    response = add(client, branch_id, "Remember: the user prefers AVIF over WebP for photos.")
    assert response.status_code == 201, response.text
    points = points_of(response.json(), branch_id)
    added = points[-1]
    assert (added["origin"], added["included"], added["text_generated"]) == ("user", True, "")
    assert added["title"] == "Remember: the user prefers AVIF"  # first five words
    assert [p["position"] for p in points] == [0, 1, 2]

    merge(client, conversation_id, [branch_id])
    say(client, conversation_id, "back on main")
    sent = provider.calls[-1][1][-1].content
    header = context.MERGE_HEADER.format(anchor_quote="Second point")
    assert sent == "\n".join(
        [
            context.BLOCK_START,
            header,
            "- X was added.",
            "- Y is solved.",
            "- Remember: the user prefers AVIF over WebP for photos.",
            context.BLOCK_END,
            "",
            "back on main",
        ]
    )


def test_a_branch_can_be_merged_with_only_points_written_by_hand(client, provider, branch):
    conversation_id, branch_id = branch
    add(client, branch_id, "My own summary.", title="mine")
    assert merge(client, conversation_id, [branch_id]).status_code == 200
    assert all(tag != "takeaway" for _, _, tag in provider.calls)  # no generation was needed


def test_generation_still_runs_when_only_user_points_exist(client, provider, branch):
    conversation_id, branch_id = branch
    add(client, branch_id, "Mine first.")
    provider.queue.append(TAKEAWAY)
    state = client.post(f"/api/branches/{branch_id}/takeaway", json={}).json()
    points = points_of(state, branch_id)
    assert [p["origin"] for p in points] == ["model", "model", "user"]
    assert [p["position"] for p in points] == [0, 1, 2]


def test_regenerate_keeps_the_points_written_by_hand(client, provider, summarised):
    conversation_id, branch_id, _ = summarised
    add(client, branch_id, "Kept one.")
    add(client, branch_id, "Kept two.")
    provider.queue.append('[{"title": "only one", "text": "A single new point."}]')
    state = client.post(f"/api/branches/{branch_id}/takeaway", json={"regenerate": True}).json()
    points = points_of(state, branch_id)
    assert [(p["origin"], p["text_final"]) for p in points] == [
        ("model", "A single new point."),
        ("user", "Kept one."),
        ("user", "Kept two."),
    ]
    assert [p["position"] for p in points] == [0, 1, 2]


def test_user_points_can_be_edited_renamed_unticked_and_deleted(client, summarised):
    conversation_id, branch_id, generated = summarised
    added = points_of(add(client, branch_id, "Draft.").json(), branch_id)[-1]

    state = client.patch(
        f"/api/points/{added['id']}", json={"text_final": "Final.", "title": "my title", "included": False}
    ).json()
    point = points_of(state, branch_id)[-1]
    assert (point["text_final"], point["title"], point["included"]) == ("Final.", "my title", False)

    state = client.delete(f"/api/points/{added['id']}").json()
    assert len(points_of(state, branch_id)) == len(generated)


def test_generated_points_cannot_be_deleted(client, summarised):
    _, _, generated = summarised
    response = client.delete(f"/api/points/{generated[0]['id']}")
    assert response.status_code == 409 and error_code(response) == "conflict"


@pytest.mark.parametrize("body", [{"text": "  "}, {"text": ""}])
def test_blank_points_are_refused(client, summarised, body):
    _, branch_id, _ = summarised
    response = client.post(f"/api/branches/{branch_id}/points", json=body)
    assert response.status_code == 422 and error_code(response) == "validation"


def test_no_points_on_closed_or_empty_branches(client, provider, summarised, chat):
    conversation_id, branch_id, _ = summarised
    merge(client, conversation_id, [branch_id])
    response = add(client, branch_id, "too late")
    assert response.status_code == 409 and error_code(response) == "conflict"

    _, answer = chat
    empty = open_branch(client, conversation_id, answer, "First point")
    response = add(client, empty, "nothing to summarise")
    assert response.status_code == 409 and error_code(response) == "conflict"
