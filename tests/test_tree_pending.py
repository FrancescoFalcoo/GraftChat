"""Tests for ``core.tree.pending_branches`` (DESIGN.md §14.5, §14.8)."""

from __future__ import annotations

import copy
from datetime import datetime

import pytest

from core.models import Branch, BranchStatus
from core.tree import pending_branches

T0 = datetime(2026, 1, 1, 12, 0, 0)

OPEN = BranchStatus.OPEN
MERGED = BranchStatus.MERGED
DISCARDED = BranchStatus.DISCARDED


def branch(id: int, status: BranchStatus = OPEN) -> Branch:
    """Build a minimal branch; only id and status matter to ``pending_branches``."""
    return Branch(
        id=id,
        conversation_id=1,
        anchor_message_id=2,
        anchor_start=0,
        anchor_end=2,
        anchor_quote="m2",
        status=status,
        merge_message_id=5 if status is MERGED else None,
        created_at=T0,
    )


def ids(branches: list[Branch]) -> list[int]:
    return [b.id for b in branches]


# --- which branches are pending ---------------------------------------------------


def test_mixed_list_keeps_only_open_branches():
    branches = [
        branch(1, OPEN),
        branch(2, MERGED),
        branch(3, OPEN),
        branch(4, DISCARDED),
        branch(5, OPEN),
    ]
    assert ids(pending_branches(branches)) == [1, 3, 5]


@pytest.mark.parametrize("status", [MERGED, DISCARDED])
def test_closed_branch_is_not_pending(status):
    # 14.5: MERGED and DISCARDED are final, the decision was taken
    assert pending_branches([branch(1, status)]) == []


def test_only_closed_branches_returns_empty_list():
    branches = [branch(1, MERGED), branch(2, DISCARDED), branch(3, MERGED)]
    assert pending_branches(branches) == []


def test_all_open_returns_all():
    branches = [branch(1), branch(2), branch(3)]
    assert pending_branches(branches) == branches


def test_empty_input_returns_empty_list():
    assert pending_branches([]) == []


def test_empty_branch_is_pending():
    # 14.8: the function receives no messages, so it cannot tell a branch with no
    # messages from one that has some. Only the status counts
    just_opened = branch(1, OPEN)
    assert pending_branches([just_opened]) == [just_opened]


# --- ordering -----------------------------------------------------------------------


def test_result_keeps_input_order():
    # ids are not monotonic: the order is the one given, not by id
    branches = [branch(7), branch(2, MERGED), branch(9), branch(1, DISCARDED), branch(4)]
    assert ids(pending_branches(branches)) == [7, 9, 4]


def test_reversed_input_gives_reversed_result():
    branches = [branch(1), branch(2, MERGED), branch(3), branch(4, DISCARDED), branch(5)]
    assert ids(pending_branches(list(reversed(branches)))) == [5, 3, 1]


# --- input and output objects ---------------------------------------------------------


def test_returns_the_original_branch_objects():
    first, closed, second = branch(1), branch(2, MERGED), branch(3)
    result = pending_branches([first, closed, second])
    assert len(result) == 2
    assert result[0] is first
    assert result[1] is second


def test_returns_a_new_list():
    branches = [branch(1), branch(2)]
    result = pending_branches(branches)
    assert result == branches  # every branch is open...
    assert result is not branches  # ...but the caller gets a list of its own
    result.clear()
    assert ids(branches) == [1, 2]


def test_does_not_mutate_input():
    branches = [branch(1), branch(2, MERGED), branch(3, DISCARDED), branch(4)]
    before = copy.deepcopy(branches)
    pending_branches(branches)
    assert branches == before
