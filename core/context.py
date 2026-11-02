"""Context builder (DESIGN.md §7).

Turns the stored tree into the exact input the model receives. Rule: what the
model sees is always exactly the checked point texts, nothing hidden.

Open questions left to the owner (not settled by DESIGN.md):
- which role merge blocks and the anchor note take: the provider (OpenRouter,
  OpenAI-compatible format) accepts system messages anywhere in the list, so
  they can be system turns or be folded into a user turn;
- whether a merged branch with no checked points renders a header-only block
  or nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Branch, Message, TakeawayPoint

MERGE_HEADER = "[merged from branch on: «{anchor_quote}»]"
ANCHOR_NOTE = (
    "The user is asking about this specific passage of your previous answer: "
    "«{anchor_quote}»"
)


@dataclass(frozen=True)
class ContextMessage:
    """One message as sent to the provider."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Context:
    """Full model input: the ordered messages, in the provider's chat format."""

    messages: list[ContextMessage]


def render_merge_block(anchor_quote: str, points: Sequence[TakeawayPoint]) -> str:
    """Render the block inserted at a merge node for one merged branch.

    Format (§7)::

        [merged from branch on: «<anchor_quote>»]
        - <text_final of point 1>
        - <text_final of point 2>

    Only points with ``included=True`` appear, ordered by ``position``,
    using ``text_final``.
    """
    raise NotImplementedError


def render_anchor_note(anchor_quote: str) -> str:
    """Render the note that tells the model which passage a branch is about."""
    raise NotImplementedError


def build_main_context(
    messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
) -> Context:
    """Build the context for the next model call on main.

    Walks main from the root to its current end. At every merge node, inserts
    the merge block of each branch merged there. Open and discarded branches
    contribute nothing.
    """
    raise NotImplementedError


def build_branch_context(
    branch: Branch,
    messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
) -> Context:
    """Build the context for the next model call inside ``branch``.

    In order (§7):
    1. main from the root up to and including the anchor message, with the
       merge blocks of any earlier merge nodes (merged take-aways propagate);
    2. the anchor note for ``branch.anchor_quote``;
    3. the branch's own messages.

    Sibling branches are never visible (isolation).
    """
    raise NotImplementedError
