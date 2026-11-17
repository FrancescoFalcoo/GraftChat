"""Tests for a branch's base: take-aways merged before a branch was opened (DESIGN.md §14.11).

Covers ``core.context.build_branch_context`` with ``base_message_id``,
``core.tree.reusable_merge_node`` and the base checks of ``check_invariants``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from core.context import BLOCK_END, BLOCK_START, build_branch_context, render_anchor_note
from core.models import Branch, BranchStatus, Message, Role, TakeawayPoint
from core.tree import InvariantError, check_invariants, open_branch, reusable_merge_node

T0 = datetime(2026, 1, 1, 12, 0, 0)
ANSWER = "1. First point.\n2. Second point.\n3. Third point."


def msg(id, parent_id, role, branch_id=None, content=None):
    return Message(id, 1, branch_id, parent_id, role, content if content is not None else f"m{id}", T0)


def branch(id, quote, status=BranchStatus.OPEN, merge_message_id=None, anchor=2, base=None):
    start = ANSWER.index(quote)
    return Branch(id, 1, anchor, start, start + len(quote), quote, status, merge_message_id, T0, base)


def point(id, branch_id, position, text, included=True):
    return TakeawayPoint(id, branch_id, position, f"t{id}", text, text, included)


def wrap(block):
    return f"{BLOCK_START}\n{block}\n{BLOCK_END}"


def scenario():
    """The case of the bug report.

    Main: 1 user, 2 answer, 3 merge node of branch 10 (opened on answer 2).
    Branch 20 is opened afterwards on another passage of the same answer 2,
    while main ends at the merge node 3.
    """
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(3, 2, Role.MERGE, content=""),
        msg(100, None, Role.USER, branch_id=10),
        msg(101, 100, Role.ASSISTANT, branch_id=10),
        msg(200, None, Role.USER, branch_id=20, content="question"),
    ]
    first = branch(10, "First point.", BranchStatus.MERGED, 3, base=2)
    second = branch(20, "Second point.", base=3)
    points = [point(1, 10, 0, "Merged fact."), point(2, 10, 1, "Unticked.", included=False)]
    return messages, [first, second], points


# --- build_branch_context -------------------------------------------------------------


def test_a_branch_opened_after_a_merge_sees_its_take_aways():
    messages, branches, points = scenario()
    context = build_branch_context(branches[1], messages, branches, points)
    first_user = context.messages[2].content
    assert "Merged fact." in first_user and "Unticked." not in first_user


def test_merged_blocks_come_before_the_anchor_note_and_the_question():
    messages, branches, points = scenario()
    context = build_branch_context(branches[1], messages, branches, points)
    assert [m.role for m in context.messages] == ["user", "assistant", "user"]
    merged = "[merged from branch on: «First point.»]\n- Merged fact."
    assert context.messages[2].content == "\n\n".join(
        [wrap(merged), wrap(render_anchor_note("Second point.")), "question"]
    )


def test_without_a_base_the_branch_stops_at_its_anchor():
    """Branches stored before §14.11 (base None) keep the old behaviour."""
    messages, branches, points = scenario()
    legacy = replace(branches[1], base_message_id=None)
    context = build_branch_context(legacy, messages, [branches[0], legacy], points)
    assert "Merged fact." not in " ".join(m.content for m in context.messages)


def test_base_equal_to_anchor_is_the_same_as_no_base():
    messages, branches, points = scenario()
    at_anchor = replace(branches[1], base_message_id=2)
    none = replace(branches[1], base_message_id=None)
    assert build_branch_context(at_anchor, messages, branches, points) == build_branch_context(
        none, messages, branches, points
    )


def test_merges_after_the_base_stay_out():
    """A sibling merged after this branch was opened is still isolated from it."""
    messages, branches, points = scenario()
    messages += [
        msg(4, 3, Role.MERGE, content=""),  # a second node: 3 is the base of branch 20
        msg(300, None, Role.USER, branch_id=30),
    ]
    late = branch(30, "Third point.", BranchStatus.MERGED, 4, base=3)
    points = points + [point(3, 30, 0, "Late fact.")]
    text = " ".join(m.content for m in build_branch_context(branches[1], messages, branches + [late], points).messages)
    assert "Merged fact." in text and "Late fact." not in text


def test_exchanges_on_main_after_the_anchor_stay_out():
    """Only take-aways cross from after the anchor: the main messages there do not."""
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(3, 2, Role.MERGE, content=""),
        msg(4, 3, Role.USER, content="a later question"),
        msg(5, 4, Role.ASSISTANT, content="a later answer"),
    ]
    first = branch(10, "First point.", BranchStatus.MERGED, 3, base=2)
    messages.append(msg(100, None, Role.USER, branch_id=10))
    second = branch(20, "Second point.", base=5)
    points = [point(1, 10, 0, "Merged fact.")]
    context = build_branch_context(second, messages, [first, second], points)
    text = " ".join(m.content for m in context.messages)
    assert "Merged fact." in text
    assert "a later question" not in text and "a later answer" not in text


def test_base_not_on_main_raises():
    messages, branches, points = scenario()
    broken = replace(branches[1], base_message_id=100)  # a branch message
    with pytest.raises(InvariantError):
        build_branch_context(broken, messages, branches, points)


# --- open_branch ------------------------------------------------------------------------


def test_open_branch_stores_the_base():
    messages, _, _ = scenario()
    b = open_branch(messages[1], 0, 3, new_id=7, created_at=T0, base_message_id=3)
    assert b.base_message_id == 3


def test_open_branch_without_base_leaves_it_unset():
    messages, _, _ = scenario()
    assert open_branch(messages[1], 0, 3, new_id=7, created_at=T0).base_message_id is None


# --- reusable_merge_node ----------------------------------------------------------------


def test_merge_node_at_the_end_is_reused_when_no_branch_started_from_it():
    messages, branches, _ = scenario()
    only_first = [branches[0]]
    assert reusable_merge_node(messages, only_first).id == 3


def test_merge_node_that_is_a_base_is_not_reused():
    messages, branches, _ = scenario()
    assert reusable_merge_node(messages, branches) is None


def test_no_merge_node_at_the_end():
    messages = [msg(1, None, Role.USER), msg(2, 1, Role.ASSISTANT, content=ANSWER)]
    assert reusable_merge_node(messages, []) is None
    assert reusable_merge_node([], []) is None


# --- check_invariants -------------------------------------------------------------------


def test_scenario_is_valid():
    check_invariants(*scenario())


def test_base_must_be_on_main():
    messages, branches, points = scenario()
    branches[1] = replace(branches[1], base_message_id=100)
    with pytest.raises(InvariantError, match="not on main"):
        check_invariants(messages, branches, points)


def test_base_cannot_come_before_the_anchor():
    messages, branches, points = scenario()
    branches[1] = replace(branches[1], base_message_id=1)
    with pytest.raises(InvariantError, match="before its anchor"):
        check_invariants(messages, branches, points)


def test_a_branch_cannot_be_merged_at_its_own_base():
    messages, branches, points = scenario()
    messages.append(msg(201, 200, Role.ASSISTANT, branch_id=20))
    branches[1] = replace(branches[1], status=BranchStatus.MERGED, merge_message_id=3)
    with pytest.raises(InvariantError, match="not after its base"):
        check_invariants(messages, branches, points)
