"""Operations and invariants on the conversation tree (DESIGN.md §5-§6).

Pure functions over ``core.models`` objects. Ids and timestamps are supplied
by the caller (assigned by persistence, which lives outside ``core``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from core.models import Branch, Message, TakeawayPoint


class InvariantError(ValueError):
    """Raised when an operation or a stored state would violate a tree invariant."""


def thread(messages: Sequence[Message], branch_id: int | None = None) -> list[Message]:
    """Return one thread's messages, ordered from its root to its current end.

    ``branch_id=None`` selects the main thread. Ordering follows ``parent_id``
    links within the thread.

    Raises:
        InvariantError: if the selected messages do not form a single chain.
    """
    raise NotImplementedError


def open_branch(
    anchor: Message,
    start: int,
    end: int,
    *,
    new_id: int,
    created_at: datetime,
) -> Branch:
    """Create an open branch anchored to ``anchor.content[start:end]``.

    The selected text is copied into ``anchor_quote``. Per DESIGN.md the anchor
    must be an assistant message on main (depth = 1, no branches of branches).

    Raises:
        InvariantError: if the anchor or the offsets are not valid.
    """
    raise NotImplementedError


def merge_branch(branch: Branch, merge_message: Message) -> Branch:
    """Return ``branch`` marked as merged at ``merge_message``.

    Per DESIGN.md the merge node is a ``merge`` message at the current end of
    main (merging anywhere else is out of scope for v1).

    Raises:
        InvariantError: if the branch is not open or the merge node is not valid.
    """
    raise NotImplementedError


def discard_branch(branch: Branch) -> Branch:
    """Return ``branch`` marked as discarded.

    A discarded branch never enters main's context.

    Raises:
        InvariantError: if the branch is not open.
    """
    raise NotImplementedError


def pending_branches(branches: Sequence[Branch]) -> list[Branch]:
    """Return the branches with no merge decision yet (drives the return-to-main banner)."""
    raise NotImplementedError


def check_invariants(
    messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
) -> None:
    """Validate the whole state of one conversation.

    Rules stated in DESIGN.md include: depth = 1; ``anchor_quote`` matches the
    anchor's selected text; a merged branch points to a ``merge`` node on main;
    ``text_generated`` is never overwritten.

    Raises:
        InvariantError: on the first violation found.
    """
    raise NotImplementedError
