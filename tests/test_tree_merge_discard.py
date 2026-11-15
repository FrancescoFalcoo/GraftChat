"""Tests for ``core.tree.merge_branch`` and ``core.tree.discard_branch`` (DESIGN.md §14.5-§14.6)."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime

import pytest

from core.models import Branch, BranchStatus, Message, Role
from core.tree import InvariantError, discard_branch, merge_branch

T0 = datetime(2026, 1, 1, 12, 0, 0)
CONV = 3

ANCHOR_ID = 2
MERGE_ID = 5
BRANCH_ID = 10  # has messages
EMPTY_BRANCH_ID = 20  # no messages
OTHER_BRANCH_ID = 30  # has messages, anchored to the same passage


def msg(
    id: int,
    parent_id: int | None,
    role: Role,
    branch_id: int | None = None,
    conversation_id: int = CONV,
) -> Message:
    return Message(
        id=id,
        conversation_id=conversation_id,
        branch_id=branch_id,
        parent_id=parent_id,
        role=role,
        content=f"m{id}",
        created_at=T0,
    )


def branch(
    id: int = BRANCH_ID,
    status: BranchStatus = BranchStatus.OPEN,
    merge_message_id: int | None = None,
    conversation_id: int = CONV,
) -> Branch:
    return Branch(
        id=id,
        conversation_id=conversation_id,
        anchor_message_id=ANCHOR_ID,
        anchor_start=0,
        anchor_end=2,
        anchor_quote="m2",
        status=status,
        merge_message_id=merge_message_id,
        created_at=T0,
    )


@pytest.fixture
def messages() -> list[Message]:
    """Main: 1 user, 2 assistant (anchor), 3 user, 4 assistant, 5 merge (end of main).

    Branch 10: 100 user, 101 assistant. Branch 30: 300 user. Branch 20: empty.
    """
    return [
        msg(1, None, Role.USER),
        msg(ANCHOR_ID, 1, Role.ASSISTANT),
        msg(3, ANCHOR_ID, Role.USER),
        msg(4, 3, Role.ASSISTANT),
        msg(MERGE_ID, 4, Role.MERGE),
        msg(100, None, Role.USER, branch_id=BRANCH_ID),
        msg(101, 100, Role.ASSISTANT, branch_id=BRANCH_ID),
        msg(300, None, Role.USER, branch_id=OTHER_BRANCH_ID),
    ]


def by_id(messages: list[Message], id: int) -> Message:
    return next(m for m in messages if m.id == id)


# =====================================================================================
# merge_branch
# =====================================================================================

# --- happy path ----------------------------------------------------------------------


def test_merge_returns_merged_branch(messages):
    b = branch()
    merged = merge_branch(b, by_id(messages, MERGE_ID), messages)
    assert merged == replace(b, status=BranchStatus.MERGED, merge_message_id=MERGE_ID)


def test_merge_keeps_all_other_fields(messages):
    b = branch()
    merged = merge_branch(b, by_id(messages, MERGE_ID), messages)
    assert merged.id == b.id
    assert merged.conversation_id == b.conversation_id
    assert merged.anchor_message_id == b.anchor_message_id
    assert (merged.anchor_start, merged.anchor_end) == (b.anchor_start, b.anchor_end)
    assert merged.anchor_quote == b.anchor_quote
    assert merged.created_at == b.created_at


def test_merge_does_not_mutate_branch(messages):
    b = branch()
    before = copy.deepcopy(b)
    merge_branch(b, by_id(messages, MERGE_ID), messages)
    assert b == before


def test_merge_does_not_mutate_messages(messages):
    before = copy.deepcopy(messages)
    merge_branch(branch(), by_id(messages, MERGE_ID), messages)
    assert messages == before


def test_merge_ignores_input_order(messages):
    shuffled = list(reversed(messages))
    merged = merge_branch(branch(), by_id(messages, MERGE_ID), shuffled)
    assert merged.status is BranchStatus.MERGED


def test_merge_accepts_equal_copy_of_merge_node(messages):
    # the caller may hold a different object for the same stored message
    node = copy.deepcopy(by_id(messages, MERGE_ID))
    merged = merge_branch(branch(), node, messages)
    assert merged.merge_message_id == MERGE_ID


def test_two_branches_can_merge_at_same_node(messages):
    node = by_id(messages, MERGE_ID)
    a = merge_branch(branch(BRANCH_ID), node, messages)
    b = merge_branch(branch(OTHER_BRANCH_ID), node, messages)
    assert a.merge_message_id == b.merge_message_id == MERGE_ID


def test_merge_with_single_message_branch(messages):
    merged = merge_branch(branch(OTHER_BRANCH_ID), by_id(messages, MERGE_ID), messages)
    assert merged.status is BranchStatus.MERGED


def test_merge_node_can_follow_another_merge_node(messages):
    # two merges in a row at the end of main
    messages.append(msg(6, MERGE_ID, Role.MERGE))
    merged = merge_branch(branch(), by_id(messages, 6), messages)
    assert merged.merge_message_id == 6


# --- branch state (14.5) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "merge_message_id"),
    [
        (BranchStatus.MERGED, MERGE_ID),  # no second merge
        (BranchStatus.DISCARDED, None),  # no merge after discard
    ],
)
def test_merge_non_open_branch_raises(messages, status, merge_message_id):
    b = branch(status=status, merge_message_id=merge_message_id)
    with pytest.raises(InvariantError):
        merge_branch(b, by_id(messages, MERGE_ID), messages)


def test_merge_empty_branch_raises(messages):
    # 14.2: an empty branch cannot be merged, only discarded
    with pytest.raises(InvariantError):
        merge_branch(branch(EMPTY_BRANCH_ID), by_id(messages, MERGE_ID), messages)


# --- invalid merge node ----------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.USER, Role.ASSISTANT])
def test_merge_node_with_wrong_role_raises(messages, role):
    # replace the end of main with a non-merge message
    messages[:] = [m for m in messages if m.id != MERGE_ID]
    node = msg(MERGE_ID, 4, role)
    messages.append(node)
    with pytest.raises(InvariantError):
        merge_branch(branch(), node, messages)


def test_merge_node_inside_a_branch_raises(messages):
    node = msg(102, 101, Role.MERGE, branch_id=BRANCH_ID)
    messages.append(node)
    with pytest.raises(InvariantError):
        merge_branch(branch(), node, messages)


def test_merge_node_from_another_conversation_raises(messages):
    messages[:] = [m for m in messages if m.id != MERGE_ID]
    node = msg(MERGE_ID, 4, Role.MERGE, conversation_id=CONV + 1)
    messages.append(node)
    with pytest.raises(InvariantError):
        merge_branch(branch(), node, messages)


def test_merge_node_not_at_end_of_main_raises(messages):
    # main continued after the merge node
    messages.append(msg(6, MERGE_ID, Role.USER))
    with pytest.raises(InvariantError):
        merge_branch(branch(), by_id(messages, MERGE_ID), messages)


def test_earlier_merge_node_raises(messages):
    # an older merge node in the middle of main cannot be reused
    messages.append(msg(6, MERGE_ID, Role.USER))
    messages.append(msg(7, 6, Role.MERGE))
    with pytest.raises(InvariantError):
        merge_branch(branch(), by_id(messages, MERGE_ID), messages)


def test_merge_node_missing_from_messages_raises(messages):
    # 14.6: the merge node must already be in messages
    node = by_id(messages, MERGE_ID)
    messages.remove(node)
    with pytest.raises(InvariantError):
        merge_branch(branch(), node, messages)


def test_corrupt_main_thread_raises(messages):
    # a fork on main: thread() must reject it
    messages.append(msg(6, 4, Role.USER))
    with pytest.raises(InvariantError):
        merge_branch(branch(), by_id(messages, MERGE_ID), messages)


# =====================================================================================
# discard_branch
# =====================================================================================


def test_discard_returns_discarded_branch():
    b = branch()
    assert discard_branch(b) == replace(b, status=BranchStatus.DISCARDED)


def test_discard_leaves_merge_message_id_none():
    assert discard_branch(branch()).merge_message_id is None


def test_discard_does_not_mutate_branch():
    b = branch()
    before = copy.deepcopy(b)
    discard_branch(b)
    assert b == before


def test_discard_empty_branch_is_allowed():
    # 14.2: an empty branch can only be discarded; discard needs no messages
    assert discard_branch(branch(EMPTY_BRANCH_ID)).status is BranchStatus.DISCARDED


@pytest.mark.parametrize(
    ("status", "merge_message_id"),
    [
        (BranchStatus.MERGED, MERGE_ID),  # no discard after merge
        (BranchStatus.DISCARDED, None),  # no double discard
    ],
)
def test_discard_non_open_branch_raises(status, merge_message_id):
    with pytest.raises(InvariantError):
        discard_branch(branch(status=status, merge_message_id=merge_message_id))


def test_merge_after_discard_raises(messages):
    discarded = discard_branch(branch())
    with pytest.raises(InvariantError):
        merge_branch(discarded, by_id(messages, MERGE_ID), messages)


def test_discard_after_merge_raises(messages):
    merged = merge_branch(branch(), by_id(messages, MERGE_ID), messages)
    with pytest.raises(InvariantError):
        discard_branch(merged)
