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
    #tengo solo i punti spuntati, nell'ordine della checklist
    included = []
    for p in points:
        if p.included:
            included.append(p)
    included.sort(key=lambda p: p.position)

    if len(included) == 0:
        return ""                                   #nessun punto spuntato: niente blocco, nemmeno l'intestazione

    lines = [MERGE_HEADER.format(anchor_quote=anchor_quote)]
    for p in included:
        lines.append(f"- {p.text_final}")           #nel contesto entra text_final, mai text_generated
    return "\n".join(lines)


def render_anchor_note(anchor_quote: str) -> str:
    """Render the note that tells the model which passage a branch is about."""
    return ANCHOR_NOTE.format(anchor_quote=anchor_quote)


def _wrap(block: str) -> str:
    """Put one block between the delimiters (§14.3)."""
    return f"{BLOCK_START}\n{block}\n{BLOCK_END}"


def _blocks_merged_at(
    node: Message, branches: Sequence[Branch], points: Sequence[TakeawayPoint]
) -> list[str]:
    """The merge blocks of the branches merged at ``node``, ordered by branch id.

    Open and discarded branches contribute nothing, and neither does a merged
    branch with no checked point.
    """
    blocks = []
    for b in sorted(branches, key=lambda b: b.id):  #ordine fisso: stesso stato -> stesso contesto
        if b.status != BranchStatus.MERGED:
            continue                                #solo i branch mergiati entrano nel main
        if b.merge_message_id != node.id:
            continue                                #mergiato, ma in un altro nodo
        own = []
        for p in points:
            if p.branch_id == b.id:
                own.append(p)
        block = render_merge_block(b.anchor_quote, own)
        if block != "":
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
    out = []
    pending = list(pending)                         #copia: non modifico la lista di chi chiama
    for m in thread_messages:
        if m.role == Role.MERGE:
            pending.extend(_blocks_merged_at(m, branches, points))
        elif m.role == Role.USER:
            #i blocchi in attesa vanno in testa a questo messaggio utente (§14.3)
            parts = []
            for block in pending:
                parts.append(_wrap(block))
            parts.append(m.content)
            out.append(ContextMessage("user", "\n\n".join(parts)))
            pending = []                            #consumati: non devono comparire due volte
        else:
            out.append(ContextMessage("assistant", m.content))
    return out, pending


def _close(out: list[ContextMessage], pending: Sequence[str]) -> Context:
    """Finish a context. Blocks still waiting become a last user message of their own.

    It happens when no user message follows them yet (main ends on a merge
    node, or a branch has no message). Dropping them would hide from the model
    something the user chose to bring back.
    """
    if len(pending) > 0:
        parts = []
        for block in pending:
            parts.append(_wrap(block))
        out.append(ContextMessage("user", "\n\n".join(parts)))
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
    main = thread(messages)                         #solo il main: i messaggi dei branch non entrano mai
    out, pending = _render(main, branches, points, [])
    return _close(out, pending)


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
    #1. il main fino all'anchor compreso: il branch non vede cosa è successo dopo
    main = thread(messages)
    upto_anchor = []
    found = False
    for m in main:
        upto_anchor.append(m)
        if m.id == branch.anchor_message_id:
            found = True
            break
    if not found:
        raise InvariantError(
            f"anchor message {branch.anchor_message_id} of branch {branch.id} is not on main"
        )
    out, pending = _render(upto_anchor, branches, points, [])

    #2. la nota sull'anchor aspetta il primo messaggio utente del branch
    pending.append(render_anchor_note(branch.anchor_quote))

    #3. i messaggi del branch. Qui non servono branches e points: un branch non
    #   contiene merge node, e i fratelli non devono essere visibili (isolamento)
    own = thread(messages, branch.id)
    own_out, pending = _render(own, [], [], pending)

    return _close(out + own_out, pending)
