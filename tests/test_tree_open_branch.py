"""Tests for ``core.tree.open_branch``."""

from __future__ import annotations

import copy
from datetime import datetime

import pytest

from core.models import Branch, BranchStatus, Message, Role
from core.tree import InvariantError, open_branch

T0 = datetime(2026, 1, 1, 12, 0, 0)
T1 = datetime(2026, 1, 1, 12, 5, 0)

CONTENT = "1. first point\n2. second point\n3. third point"


def msg(
    id: int = 7,
    parent_id: int | None = 6,
    branch_id: int | None = None,
    role: Role = Role.ASSISTANT,
    content: str = CONTENT,
    conversation_id: int = 3,
) -> Message:
    """Build a message; defaults give a valid anchor (assistant, on main)."""
    return Message(
        id=id,
        conversation_id=conversation_id,
        branch_id=branch_id,
        parent_id=parent_id,
        role=role,
        content=content,
        created_at=T0,
    )


# --- happy path ------------------------------------------------------------------


def test_returns_branch_with_all_fields():
    anchor = msg()
    start, end = CONTENT.index("second"), CONTENT.index("second") + len("second point")

    branch = open_branch(anchor, start, end, new_id=42, created_at=T1)

    assert branch == Branch(
        id=42,
        conversation_id=3,
        anchor_message_id=7,
        anchor_start=start,
        anchor_end=end,
        anchor_quote="second point",
        status=BranchStatus.OPEN,
        merge_message_id=None,
        created_at=T1,
    )


def test_anchor_message_id_is_the_anchor_id():
    branch = open_branch(msg(id=99), 0, 5, new_id=1, created_at=T1)
    assert branch.anchor_message_id == 99


def test_anchor_quote_is_the_selected_text():
    branch = open_branch(msg(), 3, 14, new_id=1, created_at=T1)
    assert branch.anchor_quote == CONTENT[3:14] == "first point"


def test_conversation_id_comes_from_anchor():
    branch = open_branch(msg(conversation_id=555), 0, 1, new_id=1, created_at=T1)
    assert branch.conversation_id == 555


def test_new_branch_is_open_and_not_merged():
    branch = open_branch(msg(), 0, 1, new_id=1, created_at=T1)
    assert branch.status is BranchStatus.OPEN
    assert branch.merge_message_id is None


def test_uses_supplied_id_and_timestamp():
    branch = open_branch(msg(), 0, 1, new_id=1234, created_at=T1)
    assert branch.id == 1234
    assert branch.created_at == T1


def test_select_whole_message():
    anchor = msg()
    branch = open_branch(anchor, 0, len(CONTENT), new_id=1, created_at=T1)
    assert branch.anchor_quote == CONTENT


def test_select_single_character():
    branch = open_branch(msg(content="abc"), 1, 2, new_id=1, created_at=T1)
    assert branch.anchor_quote == "b"


def test_select_last_character():
    branch = open_branch(msg(content="abc"), 2, 3, new_id=1, created_at=T1)
    assert branch.anchor_quote == "c"


def test_offsets_count_characters_not_bytes():
    content = "perché è così 🌱 ok"
    start = content.index("🌱")
    branch = open_branch(msg(content=content), start, start + 1, new_id=1, created_at=T1)
    assert branch.anchor_quote == "🌱"


def test_anchor_can_be_main_root():
    # an assistant message with parent_id=None is still a valid anchor
    branch = open_branch(msg(parent_id=None), 0, 1, new_id=1, created_at=T1)
    assert branch.anchor_message_id == 7


def test_does_not_mutate_anchor():
    anchor = msg()
    before = copy.deepcopy(anchor)
    open_branch(anchor, 0, 5, new_id=1, created_at=T1)
    assert anchor == before


def test_two_branches_on_same_passage_are_independent():
    anchor = msg()
    a = open_branch(anchor, 0, 5, new_id=1, created_at=T1)
    b = open_branch(anchor, 0, 5, new_id=2, created_at=T1)
    assert a.id != b.id
    assert a.anchor_quote == b.anchor_quote


# --- invalid anchor -------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.USER, Role.MERGE])
def test_non_assistant_anchor_raises(role):
    with pytest.raises(InvariantError):
        open_branch(msg(role=role), 0, 1, new_id=1, created_at=T1)


def test_anchor_inside_a_branch_raises():
    # depth = 1: no branches of branches
    with pytest.raises(InvariantError):
        open_branch(msg(branch_id=10), 0, 1, new_id=1, created_at=T1)


# --- invalid offsets ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (5, 5),  # empty selection
        (6, 5),  # reversed
        (-1, 3),  # negative start
        (-3, -1),  # negative both (Python slicing would accept it)
        (0, len(CONTENT) + 1),  # end past the end
        (len(CONTENT), len(CONTENT) + 1),  # start at the end
        (0, 0),  # empty at the beginning
    ],
)
def test_invalid_offsets_raise(start, end):
    with pytest.raises(InvariantError, match="invalid selection"):
        open_branch(msg(), start, end, new_id=1, created_at=T1)


def test_empty_content_has_no_valid_selection():
    with pytest.raises(InvariantError):
        open_branch(msg(content=""), 0, 0, new_id=1, created_at=T1)


def test_invariant_error_is_a_value_error():
    with pytest.raises(ValueError):
        open_branch(msg(role=Role.USER), 0, 1, new_id=1, created_at=T1)
