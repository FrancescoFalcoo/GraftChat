"""Tests for ``core.tree.check_invariants`` (DESIGN.md §6, §14)."""

from __future__ import annotations

import copy
import random
from dataclasses import replace
from datetime import datetime

import pytest

from core.models import Branch, BranchStatus, Message, Role, TakeawayPoint
from core.tree import InvariantError, check_invariants

T0 = datetime(2026, 1, 1, 12, 0, 0)
ANSWER = "1. First point.\n2. Second point.\n3. Third point."
LATER = "A later answer, with its own passage."


def msg(id, parent_id, role, branch_id=None, content=None, conversation_id=1):
    text = content if content is not None else f"m{id}"
    return Message(id, conversation_id, branch_id, parent_id, role, text, T0)


def branch(id, anchor, content, quote, status=BranchStatus.OPEN, merge_message_id=None):
    start = content.index(quote)
    return Branch(id, 1, anchor, start, start + len(quote), quote, status, merge_message_id, T0)


def point(id, branch_id, position, included=True):
    return TakeawayPoint(id, branch_id, position, f"t{id}", f"g{id}", f"g{id}", included)


def valid_state():
    """Main 1-2-3-4-5(merge)-6-7. Branch 10 merged at 5, 20 open, 30 discarded and empty."""
    messages = [
        msg(1, None, Role.USER),
        msg(2, 1, Role.ASSISTANT, content=ANSWER),
        msg(3, 2, Role.USER),
        msg(4, 3, Role.ASSISTANT, content=LATER),
        msg(5, 4, Role.MERGE, content=""),
        msg(6, 5, Role.USER),
        msg(7, 6, Role.ASSISTANT),
        msg(100, None, Role.USER, branch_id=10),
        msg(101, 100, Role.ASSISTANT, branch_id=10),
        msg(200, None, Role.USER, branch_id=20),
    ]
    branches = [
        branch(10, 2, ANSWER, "Second point.", BranchStatus.MERGED, 5),
        branch(20, 2, ANSWER, "Third point."),
        branch(30, 4, LATER, "own passage", BranchStatus.DISCARDED),
    ]
    points = [point(1, 10, 0), point(2, 10, 1), point(3, 20, 0)]
    return messages, branches, points


def by_id(items, id):
    return next(i for i, item in enumerate(items) if item.id == id)


def set_msg(state, id, **changes):
    messages, branches, points = state
    messages[by_id(messages, id)] = replace(messages[by_id(messages, id)], **changes)


def set_branch(state, id, **changes):
    messages, branches, points = state
    branches[by_id(branches, id)] = replace(branches[by_id(branches, id)], **changes)


# --- valid states -------------------------------------------------------------------------


def test_valid_state_passes():
    assert check_invariants(*valid_state()) is None


def test_empty_state_passes():
    check_invariants([], [], [])


def test_messages_only_pass():
    check_invariants(valid_state()[0][:7], [], [])


def test_input_order_does_not_matter():
    messages, branches, points = valid_state()
    rng = random.Random(0)
    for items in (messages, branches, points):
        rng.shuffle(items)
    check_invariants(messages, branches, points)


def test_does_not_mutate():
    state = valid_state()
    before = copy.deepcopy(state)
    check_invariants(*state)
    assert state == before


def test_discarded_branch_may_keep_its_points():
    messages, branches, points = valid_state()
    messages.append(msg(300, None, Role.USER, branch_id=30))
    check_invariants(messages, branches, points + [point(9, 30, 0)])  # §14.9


def test_two_branches_merged_at_one_node():
    state = valid_state()
    set_branch(state, 20, status=BranchStatus.MERGED, merge_message_id=5)
    check_invariants(*state)


def test_same_position_in_two_branches_is_fine():
    messages, branches, points = valid_state()
    assert {(p.branch_id, p.position) for p in points} >= {(10, 0), (20, 0)}
    check_invariants(messages, branches, points)


def test_edited_unchecked_or_empty_take_aways_are_fine():
    messages, branches, points = valid_state()
    points = [replace(p, text_final="edited", included=False) for p in points]  # §14.4, §14.7
    check_invariants(messages, branches, points)


# --- one broken rule at a time ---------------------------------------------------------------


def dup_message(s):
    s[0].append(msg(7, 6, Role.ASSISTANT))


def dup_branch(s):
    s[1].append(replace(s[1][1]))


def dup_point(s):
    s[2].append(point(1, 20, 5))


def other_conversation_message(s):
    set_msg(s, 7, conversation_id=2)


def other_conversation_branch(s):
    set_branch(s, 20, conversation_id=2)


def orphan_message(s):
    s[0].append(msg(900, None, Role.USER, branch_id=99))


def merge_inside_branch(s):
    s[0].append(msg(102, 101, Role.MERGE, branch_id=10, content=""))


def two_roots_on_main(s):
    s[0].append(msg(8, None, Role.USER))


def fork_on_main(s):
    s[0].append(msg(8, 6, Role.ASSISTANT))


def missing_parent_on_main(s):
    s[0].append(msg(8, 99, Role.USER))


def broken_branch_thread(s):
    s[0].append(msg(102, 100, Role.ASSISTANT, branch_id=10))


def anchor_missing(s):
    set_branch(s, 20, anchor_message_id=999)


def anchor_in_branch(s):
    s[0].append(msg(201, 200, Role.ASSISTANT, branch_id=20, content=ANSWER))
    set_branch(s, 30, anchor_message_id=201, anchor_start=0, anchor_end=2, anchor_quote="1.")


def anchor_is_user(s):
    set_branch(s, 20, anchor_message_id=3, anchor_start=0, anchor_end=2, anchor_quote="m3")


def anchor_is_merge(s):
    set_branch(s, 20, anchor_message_id=5, anchor_start=0, anchor_end=0, anchor_quote="")


def negative_start(s):
    set_branch(s, 20, anchor_start=-1)


def end_past_content(s):
    set_branch(s, 20, anchor_end=len(ANSWER) + 1)


def empty_selection(s):
    set_branch(s, 20, anchor_end=s[1][1].anchor_start)


def reversed_selection(s):
    b = s[1][1]
    set_branch(s, 20, anchor_start=b.anchor_end, anchor_end=b.anchor_start)


def wrong_quote(s):
    set_branch(s, 20, anchor_quote="something else")


def open_with_merge_node(s):
    set_branch(s, 20, merge_message_id=5)


def discarded_with_merge_node(s):
    set_branch(s, 30, merge_message_id=5)


def merged_without_merge_node(s):
    set_branch(s, 10, merge_message_id=None)


def merge_node_missing(s):
    set_branch(s, 10, merge_message_id=999)


def merge_node_is_assistant(s):
    set_branch(s, 10, merge_message_id=7)


def merge_node_in_branch(s):
    set_branch(s, 10, merge_message_id=101)


def merged_empty_branch(s):
    set_branch(s, 30, status=BranchStatus.MERGED, merge_message_id=5)


def merge_node_before_anchor(s):
    # move branch 30 (anchored at 4) so that it is merged at an earlier merge node
    messages = s[0]
    set_msg(s, 3, parent_id=9)
    messages.append(msg(9, 2, Role.MERGE, content=""))
    messages.append(msg(300, None, Role.USER, branch_id=30))
    set_branch(s, 30, status=BranchStatus.MERGED, merge_message_id=9)


def point_of_missing_branch(s):
    s[2].append(point(9, 99, 0))


def same_position_twice(s):
    s[2].append(point(9, 10, 1))


BREAKERS = [
    dup_message, dup_branch, dup_point,
    other_conversation_message, other_conversation_branch,
    orphan_message, merge_inside_branch,
    two_roots_on_main, fork_on_main, missing_parent_on_main, broken_branch_thread,
    anchor_missing, anchor_in_branch, anchor_is_user, anchor_is_merge,
    negative_start, end_past_content, empty_selection, reversed_selection, wrong_quote,
    open_with_merge_node, discarded_with_merge_node, merged_without_merge_node,
    merge_node_missing, merge_node_is_assistant, merge_node_in_branch,
    merged_empty_branch, merge_node_before_anchor,
    point_of_missing_branch, same_position_twice,
]


@pytest.mark.parametrize("breaker", BREAKERS, ids=[b.__name__ for b in BREAKERS])
def test_each_broken_rule_raises(breaker):
    state = valid_state()
    breaker(state)
    with pytest.raises(InvariantError):
        check_invariants(*state)
