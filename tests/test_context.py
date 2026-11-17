"""Tests for ``core.context`` (DESIGN.md §7, §14.3, §14.4, §14.10)."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime

import pytest

from core.context import (
    ANCHOR_NOTE,
    BLOCK_END,
    BLOCK_START,
    MERGE_HEADER,
    build_branch_context,
    build_main_context,
    render_anchor_note,
    render_merge_block,
)
from core.models import Branch, BranchStatus, Message, Role, TakeawayPoint
from core.tree import InvariantError

T0 = datetime(2026, 1, 1, 12, 0, 0)
ANSWER = "1. First point.\n2. Second point.\n3. Third point."


def msg(id, parent_id, role, branch_id=None, content=None):
    return Message(id, 1, branch_id, parent_id, role, content if content is not None else f"m{id}", T0)


def branch(id, quote, status=BranchStatus.OPEN, merge_message_id=None, anchor=2):
    start = ANSWER.index(quote)
    return Branch(id, 1, anchor, start, start + len(quote), quote, status, merge_message_id, T0)


def point(id, branch_id, position, text, included=True, generated=None):
    return TakeawayPoint(id, branch_id, position, f"t{id}", generated or text, text, included)


def wrap(block):
    return f"{BLOCK_START}\n{block}\n{BLOCK_END}"


def roles(context):
    return [m.role for m in context.messages]


def contents(context):
    return [m.content for m in context.messages]


# --- render_merge_block / render_anchor_note -----------------------------------------


def test_merge_block_format():
    points = [point(1, 10, 0, "A."), point(2, 10, 1, "B.")]
    assert render_merge_block("q", points) == "\n".join(
        [MERGE_HEADER.format(anchor_quote="q"), "- A.", "- B."]
    )


def test_merge_block_orders_by_position_and_keeps_only_included():
    points = [point(1, 10, 2, "C."), point(2, 10, 0, "A."), point(3, 10, 1, "B.", included=False)]
    assert render_merge_block("q", points).split("\n")[1:] == ["- A.", "- C."]


def test_merge_block_uses_text_final():
    edited = point(1, 10, 0, "my words", generated="model words")
    block = render_merge_block("q", [edited])
    assert "my words" in block and "model words" not in block


@pytest.mark.parametrize("points", [[], [point(1, 10, 0, "A.", included=False)]])
def test_merge_block_without_included_points_is_empty(points):
    assert render_merge_block("q", points) == ""  # §14.4


def test_texts_are_rendered_verbatim():
    odd = 'braces {x} "quotes" «guillemets»\nnew line'
    assert odd in render_merge_block(odd, [point(1, 10, 0, odd)])
    assert render_anchor_note(odd) == ANCHOR_NOTE.format(anchor_quote=odd)


def test_anchor_note():
    assert render_anchor_note("Second point.") == ANCHOR_NOTE.format(anchor_quote="Second point.")


# --- build_main_context ------------------------------------------------------------------


def plain_main():
    return [msg(1, None, Role.USER), msg(2, 1, Role.ASSISTANT, content=ANSWER), msg(3, 2, Role.USER)]


def test_plain_main_is_passed_through():
    context = build_main_context(plain_main(), [], [])
    assert roles(context) == ["user", "assistant", "user"]
    assert contents(context) == ["m1", ANSWER, "m3"]


def test_empty_conversation_gives_empty_context():
    assert build_main_context([], [], []).messages == []


@pytest.fixture
def merged():
    """Main 1-2-5(merge)-6-7-8; branch 10 merged at 5 with one checked point."""
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(5, 2, Role.MERGE, content=""),
        msg(6, 5, Role.USER, content="next"),
        msg(7, 6, Role.ASSISTANT),
        msg(8, 7, Role.USER, content="later"),
        msg(100, None, Role.USER, branch_id=10, content="branch secret"),
        msg(101, 100, Role.ASSISTANT, branch_id=10),
    ]
    branches = [branch(10, "Second point.", BranchStatus.MERGED, 5)]
    points = [point(1, 10, 0, "Kept."), point(2, 10, 1, "Unchecked.", included=False)]
    return messages, branches, points


def test_merge_block_is_prepended_once_to_the_next_user_message(merged):
    context = build_main_context(*merged)
    block = render_merge_block("Second point.", merged[2])
    assert roles(context) == ["user", "assistant", "user", "assistant", "user"]
    assert context.messages[2].content == f"{wrap(block)}\n\nnext"
    assert context.messages[4].content == "later"
    assert "system" not in roles(context)  # §14.3


def test_branch_messages_never_reach_main(merged):
    assert "branch secret" not in " ".join(contents(build_main_context(*merged)))


@pytest.mark.parametrize("status", [BranchStatus.OPEN, BranchStatus.DISCARDED])
def test_open_and_discarded_branches_contribute_nothing(merged, status):
    messages, _, points = merged
    other = [branch(10, "Second point.", status)]
    assert contents(build_main_context(messages, other, points))[2] == "next"


def test_merged_branch_without_checked_points_contributes_nothing(merged):
    messages, branches, points = merged
    unchecked = [replace(p, included=False) for p in points]
    assert contents(build_main_context(messages, branches, unchecked))[2] == "next"


def test_two_branches_at_one_node_are_ordered_by_branch_id(merged):
    messages, branches, points = merged
    messages = messages + [msg(200, None, Role.USER, branch_id=20)]
    second = branch(20, "Third point.", BranchStatus.MERGED, 5)
    points = points + [point(3, 20, 0, "From twenty.")]
    first_block = render_merge_block("Second point.", points[:2])
    second_block = render_merge_block("Third point.", points[2:])
    for order in ([branches[0], second], [second, branches[0]]):
        sent = build_main_context(messages, order, points).messages[2].content
        assert sent == f"{wrap(first_block)}\n\n{wrap(second_block)}\n\nnext"


def test_blocks_of_consecutive_merge_nodes_accumulate():
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(5, 2, Role.MERGE, content=""),
        msg(6, 5, Role.MERGE, content=""),
        msg(7, 6, Role.USER, content="next"),
        msg(100, None, Role.USER, branch_id=10),
        msg(200, None, Role.USER, branch_id=20),
    ]
    branches = [
        branch(20, "Second point.", BranchStatus.MERGED, 5),
        branch(10, "Third point.", BranchStatus.MERGED, 6),
    ]
    points = [point(1, 10, 0, "Ten."), point(2, 20, 0, "Twenty.")]
    sent = build_main_context(messages, branches, points).messages[-1].content
    assert sent.index("Twenty.") < sent.index("Ten.") < sent.index("next")  # main order


def test_main_ending_on_a_merge_node_keeps_the_block(merged):
    messages, branches, points = merged
    messages = [m for m in messages if m.id not in (6, 7, 8)]
    context = build_main_context(messages, branches, points)
    assert context.messages[-1].role == "user"
    assert context.messages[-1].content == wrap(render_merge_block("Second point.", points))


def test_main_context_ignores_input_order_and_does_not_mutate(merged):
    messages, branches, points = merged
    before = copy.deepcopy(merged)
    expected = build_main_context(messages, branches, points)
    shuffled = build_main_context(messages[::-1], branches[::-1], points[::-1])
    assert shuffled == expected
    assert (messages, branches, points) == before


# --- build_branch_context ----------------------------------------------------------------


@pytest.fixture
def tree():
    """Main 1-2(anchor)-3-4; branch 10 on 2 with two exchanges; sibling 20 on 2."""
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(3, 2, Role.USER, content="after anchor"),
        msg(4, 3, Role.ASSISTANT),
        msg(100, None, Role.USER, branch_id=10, content="why?"),
        msg(101, 100, Role.ASSISTANT, branch_id=10),
        msg(102, 101, Role.USER, branch_id=10, content="more?"),
        msg(200, None, Role.USER, branch_id=20, content="sibling secret"),
    ]
    branches = [branch(10, "Second point."), branch(20, "Third point.")]
    return messages, branches, []


def test_branch_context_order_and_anchor_note(tree):
    messages, branches, points = tree
    context = build_branch_context(branches[0], messages, branches, points)
    note = wrap(render_anchor_note("Second point."))
    assert roles(context) == ["user", "assistant", "user", "assistant", "user"]
    assert contents(context) == ["m1", ANSWER, f"{note}\n\nwhy?", "m101", "more?"]


def test_branch_does_not_see_main_after_the_anchor_or_siblings(tree):
    text = " ".join(contents(build_branch_context(tree[1][0], *tree)))
    assert "after anchor" not in text and "sibling secret" not in text


@pytest.mark.parametrize("status", [BranchStatus.OPEN, BranchStatus.DISCARDED])
def test_siblings_stay_invisible_in_any_state(tree, status):
    messages, branches, points = tree
    sibling = replace(branches[1], status=status)
    text = " ".join(contents(build_branch_context(branches[0], messages, [branches[0], sibling], points)))
    assert "sibling secret" not in text


def test_empty_branch_gets_the_note_as_last_message(tree):
    messages, branches, points = tree
    empty = branch(30, "First point.")
    context = build_branch_context(empty, messages, branches + [empty], points)
    assert contents(context) == ["m1", ANSWER, wrap(render_anchor_note("First point."))]


def test_take_aways_merged_before_the_anchor_propagate():
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(5, 2, Role.MERGE, content=""),
        msg(6, 5, Role.USER, content="next"),
        msg(7, 6, Role.ASSISTANT, content=ANSWER),
        msg(8, 7, Role.MERGE, content=""),
        msg(100, None, Role.USER, branch_id=10),
        msg(200, None, Role.USER, branch_id=20),
        msg(300, None, Role.USER, branch_id=30, content="question"),
    ]
    early = branch(10, "Second point.", BranchStatus.MERGED, 5)
    late = branch(20, "First point.", BranchStatus.MERGED, 8)
    current = branch(30, "Third point.", anchor=7)
    points = [point(1, 10, 0, "Early point."), point(2, 20, 0, "Late point.")]
    text = " ".join(contents(build_branch_context(current, messages, [early, late, current], points)))
    assert "Early point." in text and "Late point." not in text


@pytest.mark.parametrize("status", [BranchStatus.MERGED, BranchStatus.DISCARDED])
def test_closed_branch_context_is_built_the_same_way(tree, status):
    messages, branches, points = tree
    closed = replace(branches[0], status=status)
    assert build_branch_context(closed, *tree) == build_branch_context(branches[0], *tree)


@pytest.mark.parametrize("anchor", [999, 100])
def test_anchor_not_on_main_raises(tree, anchor):
    messages, branches, points = tree
    bad = replace(branches[0], anchor_message_id=anchor)
    with pytest.raises(InvariantError):
        build_branch_context(bad, messages, branches, points)


def test_branch_context_does_not_mutate(tree):
    before = copy.deepcopy(tree)
    build_branch_context(tree[1][0], *tree)
    assert tree == before
