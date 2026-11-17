"""Context builder (DESIGN.md §7).

Turns the stored tree into the exact input the model receives. Rule: what the
model sees is always exactly the checked point texts, nothing hidden.

Decisions applied here (DESIGN.md §14):
- merge blocks and the anchor note are never separate ``system`` messages: they
  are prepended, between explicit delimiters, to the next user message (§14.3);
- a merged branch with no checked point renders nothing, not even the header
  (§14.4);
- the same state always gives the same context: blocks of branches merged at
  the same node are ordered by branch id (§14.10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from core.models import Branch, BranchStatus, Message, Role, TakeawayPoint
from core.tree import InvariantError, thread

MERGE_HEADER = "[merged from branch on: «{anchor_quote}»]"
ANCHOR_NOTE = (
    "The user is asking about this specific passage of your previous answer: "
    "«{anchor_quote}»"
)

# Delimiters around every block the app adds to a user message (§14.3). They
# tell the model, and whoever reads the logs, which text the user did not type.
BLOCK_START = "<context>"
BLOCK_END = "</context>"


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

    ``points`` are the points of that one branch. Only points with
    ``included=True`` appear, ordered by ``position``, using ``text_final``.

    Returns the empty string when no point is included: a merge with zero
    checked points injects nothing (§14.4).
    """
    #keep only the checked points, in the order of the checklist
    included = []                                   #the points that will enter the context
    for p in points:
        if p.included:                              #ticked in the checklist
            included.append(p)
    included.sort(key=lambda p: p.position)         #same order as the checklist rows

    if len(included) == 0:
        return ""                                   #no checked point: no block at all, not even the header (§14.4)

    lines = [MERGE_HEADER.format(anchor_quote=anchor_quote)]   #first line: which passage the branch was about
    for p in included:
        lines.append(f"- {p.text_final}")           #text_final enters the context, never text_generated
    return "\n".join(lines)                         #one line per point under the header


def render_anchor_note(anchor_quote: str) -> str:
    """Render the note that tells the model which passage a branch is about."""
    return ANCHOR_NOTE.format(anchor_quote=anchor_quote)   #the fixed sentence with the quote inserted


def _wrap(block: str) -> str:
    """Put one block between the delimiters (§14.3)."""
    return f"{BLOCK_START}\n{block}\n{BLOCK_END}"     #<context> on its own line, the block, </context>


def _blocks_merged_at(
    node: Message, branches: Sequence[Branch], points: Sequence[TakeawayPoint]
) -> list[str]:
    """The merge blocks of the branches merged at ``node``, ordered by branch id.

    Open and discarded branches contribute nothing, and neither does a merged
    branch with no checked point.
    """
    blocks = []                                     #one block per branch merged at this node
    for b in sorted(branches, key=lambda b: b.id):  #fixed order: same state -> same context (§14.10)
        if b.status != BranchStatus.MERGED:
            continue                                #only merged branches enter main
        if b.merge_message_id != node.id:
            continue                                #merged, but at another node
        own = []                                    #the points of this branch only
        for p in points:
            if p.branch_id == b.id:
                own.append(p)
        block = render_merge_block(b.anchor_quote, own)
        if block != "":                             #empty when no point is checked: skip it (§14.4)
            blocks.append(block)
    return blocks


def _render(
    thread_messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
    pending: Sequence[str],
) -> tuple[list[ContextMessage], list[str]]:
    """Turn one thread, already in order, into provider messages.

    ``pending`` holds the blocks waiting for a user message to be prepended to.
    A merge node is never sent as a message: it only adds its blocks to the
    waiting ones. Returns the messages and the blocks still waiting at the end.
    """
    out = []                                        #the messages for the provider, in order
    pending = list(pending)                         #copy: the caller's list is not modified
    for m in thread_messages:
        if m.role == Role.MERGE:                    #a merge node is not a message for the model...
            pending.extend(_blocks_merged_at(m, branches, points))  #...it only adds blocks to the waiting ones
        elif m.role == Role.USER:
            #the waiting blocks go in front of this user message (§14.3)
            parts = []
            for block in pending:
                parts.append(_wrap(block))          #each block between its own delimiters
            parts.append(m.content)                 #then what the user typed
            out.append(ContextMessage("user", "\n\n".join(parts)))   #parts separated by a blank line
            pending = []                            #used up: they must not appear twice
        else:
            out.append(ContextMessage("assistant", m.content))     #answers of the model go through unchanged
    return out, pending                             #pending: blocks with no user message after them yet


def _close(out: list[ContextMessage], pending: Sequence[str]) -> Context:
    """Finish a context. Blocks still waiting become a last user message of their own.

    It happens when no user message follows them yet (main ends on a merge
    node, or a branch has no message). Dropping them would hide from the model
    something the user chose to bring back.
    """
    if len(pending) > 0:                            #some blocks never found a user message
        parts = []
        for block in pending:
            parts.append(_wrap(block))
        out.append(ContextMessage("user", "\n\n".join(parts)))   #a last user message with only the blocks
    return Context(out)


def build_main_context(
    messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
) -> Context:
    """Build the context for the next model call on main.

    Walks main from the root to its current end. At every merge node, inserts
    the merge block of each branch merged there, prepended to the next user
    message. Open and discarded branches contribute nothing.
    """
    main = thread(messages)                         #main only: branch messages never enter
    out, pending = _render(main, branches, points, [])  #walk main, collecting merge blocks at merge nodes
    return _close(out, pending)                     #blocks left at the end become a message of their own


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
    2. the anchor note for ``branch.anchor_quote``, prepended to the branch's
       first user message;
    3. the branch's own messages.

    Sibling branches are never visible (isolation).

    Raises:
        InvariantError: if the branch's anchor message is not on main.
    """
    #1. main up to and including the anchor: the branch does not see what happened after it
    main = thread(messages)                         #main in order
    upto_anchor = []                                #the part of main the branch can see
    found = False
    for m in main:
        upto_anchor.append(m)
        if m.id == branch.anchor_message_id:        #stop at the anchor, keeping it
            found = True
            break
    if not found:                                   #the anchor is not on main: corrupt branch
        raise InvariantError(
            f"anchor message {branch.anchor_message_id} of branch {branch.id} is not on main"
        )
    out, pending = _render(upto_anchor, branches, points, [])  #take-aways merged before the anchor propagate

    #2. the anchor note waits for the first user message of the branch
    pending.append(render_anchor_note(branch.anchor_quote))

    #3. the branch's own messages. No branches or points needed here: a branch has
    #   no merge nodes, and siblings must not be visible (isolation)
    own = thread(messages, branch.id)               #this branch only, in order
    own_out, pending = _render(own, [], [], pending)

    return _close(out + own_out, pending)           #empty branch: the note becomes the last message
