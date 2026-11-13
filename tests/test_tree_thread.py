"""Tests for ``core.tree.thread``."""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from core.models import Message, Role
from core.tree import InvariantError, thread

T0 = datetime(2026, 1, 1, 12, 0, 0)


def msg(id: int, parent_id: int | None, branch_id: int | None = None) -> Message:
    """Build a minimal message; only id, parent_id and branch_id matter to ``thread``."""
    return Message(
        id=id,
        conversation_id=1,
        branch_id=branch_id,
        parent_id=parent_id,
        role=Role.USER,
        content=f"m{id}",
        created_at=T0,
    )


def ids(messages: list[Message]) -> list[int]:
    return [m.id for m in messages]


# --- empty / trivial cases ---------------------------------------------------


def test_empty_input_returns_empty_list():
    assert thread([]) == []


def test_unknown_branch_returns_empty_list():
    messages = [msg(1, None), msg(2, 1)]
    assert thread(messages, branch_id=99) == []


def test_single_root_message():
    assert ids(thread([msg(1, None)])) == [1]


# --- ordering -----------------------------------------------------------------


def test_chain_already_in_order():
    messages = [msg(1, None), msg(2, 1), msg(3, 2), msg(4, 3)]
    assert ids(thread(messages)) == [1, 2, 3, 4]


def test_chain_in_reverse_order():
    messages = [msg(4, 3), msg(3, 2), msg(2, 1), msg(1, None)]
    assert ids(thread(messages)) == [1, 2, 3, 4]


def test_chain_shuffled():
    messages = [msg(i, i - 1 if i > 1 else None) for i in range(1, 21)]
    random.Random(0).shuffle(messages)
    assert ids(thread(messages)) == list(range(1, 21))


def test_ordering_follows_parent_links_not_ids():
    # ids are not monotonic along the chain
    messages = [msg(7, None), msg(3, 7), msg(9, 3), msg(1, 9)]
    assert ids(thread(messages)) == [7, 3, 9, 1]


def test_returns_the_original_message_objects():
    root, child = msg(1, None), msg(2, 1)
    result = thread([child, root])
    assert result[0] is root
    assert result[1] is child


def test_does_not_mutate_input():
    messages = [msg(2, 1), msg(1, None)]
    snapshot = list(messages)
    thread(messages)
    assert messages == snapshot


# --- branch selection -----------------------------------------------------------


@pytest.fixture
def conversation() -> list[Message]:
    """Main thread 1-2-3, branch 10 with 100-101, branch 20 with 200."""
    return [
        msg(1, None),
        msg(100, None, branch_id=10),
        msg(2, 1),
        msg(200, None, branch_id=20),
        msg(101, 100, branch_id=10),
        msg(3, 2),
    ]


def test_default_selects_main_thread(conversation):
    assert ids(thread(conversation)) == [1, 2, 3]


def test_explicit_none_selects_main_thread(conversation):
    assert ids(thread(conversation, branch_id=None)) == [1, 2, 3]


def test_selects_one_branch(conversation):
    assert ids(thread(conversation, branch_id=10)) == [100, 101]


def test_selects_single_message_branch(conversation):
    assert ids(thread(conversation, branch_id=20)) == [200]


def test_branch_messages_do_not_break_main_chain():
    # Branch messages have their own root (parent_id=None): they must not
    # count as a second root of main.
    messages = [msg(1, None), msg(2, 1), msg(50, None, branch_id=5)]
    assert ids(thread(messages)) == [1, 2]


# --- invariant violations ---------------------------------------------------------


def test_two_roots_raises():
    with pytest.raises(InvariantError, match="expected 1 root, found 2"):
        thread([msg(1, None), msg(2, None)])


def test_no_root_raises():
    # 1 <-> 2 cycle: nobody has parent_id=None
    with pytest.raises(InvariantError, match="expected 1 root, found 0"):
        thread([msg(1, 2), msg(2, 1)])


def test_fork_raises():
    # 2 and 3 both claim 1 as parent
    with pytest.raises(InvariantError, match="two messages have parent 1"):
        thread([msg(1, None), msg(2, 1), msg(3, 1)])


def test_parent_missing_from_thread_raises():
    # 3 points to a message that does not exist
    with pytest.raises(InvariantError, match="inconsistent walk"):
        thread([msg(1, None), msg(2, 1), msg(3, 99)])


def test_parent_in_another_thread_raises():
    # 101 is in branch 10 but its parent is on main
    messages = [msg(1, None), msg(100, None, branch_id=10), msg(101, 1, branch_id=10)]
    with pytest.raises(InvariantError, match="inconsistent walk"):
        thread(messages, branch_id=10)


def test_detached_cycle_raises():
    # valid chain 1-2 plus a cycle 5 <-> 6 not reachable from the root
    messages = [msg(1, None), msg(2, 1), msg(5, 6), msg(6, 5)]
    with pytest.raises(InvariantError, match="inconsistent walk"):
        thread(messages)


def test_self_parent_raises():
    with pytest.raises(InvariantError, match="inconsistent walk"):
        thread([msg(1, None), msg(2, 2)])


def test_invariant_error_is_a_value_error():
    with pytest.raises(ValueError):
        thread([msg(1, None), msg(2, None)])
