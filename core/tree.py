"""Operations and invariants on the conversation tree (DESIGN.md §5-§6).

Pure functions over ``core.models`` objects. Ids and timestamps are supplied
by the caller (assigned by persistence, which lives outside ``core``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from core.models import Branch, BranchStatus, Message, Role, TakeawayPoint


class InvariantError(ValueError):
    """Raised when an operation or a stored state would violate a tree invariant."""


def thread(messages: Sequence[Message], branch_id: int | None = None) -> list[Message]:
    """Return one thread's messages, ordered from its root to its current end.

    ``branch_id=None`` selects the main thread. Ordering follows ``parent_id``
    links within the thread.

    Raises:
        InvariantError: if the selected messages do not form a single chain.
    """
    result = []                                 #empty list where we collect the messages of this thread
    root = []                                   #messages with no parent: a valid thread has exactly one

    #build the list of messages
    for m in messages:                          #go through every message of the conversation
        if m.branch_id==branch_id:              #keep only the ones of the requested thread (None = main); no getters needed, unlike java
            result.append(m)                    #our list now holds every message of this thread
    if len(result)== 0:
        return []                               #empty thread: an empty list, not an error (§14.2)

    #find the root
    for m in result:
        if m.parent_id is None:                 #among them, look for the first node of the thread
            root.append(m)

    if len(root)!= 1:                           #zero roots (a cycle) or two roots: not a single chain
        raise InvariantError(f"expected 1 root, found {len(root)}")

    #build the dictionary: order does not matter, what matters is linking every parent to its child
    path = {}                                   #parent id -> child message: the chain is rebuilt from here
    for m in result:
        if m.parent_id is not None:             #the root has no parent, so it is never a child
            if m.parent_id in path:             #that parent already has a child: this would be a fork
                raise InvariantError(f"two messages have parent {m.parent_id}")
            path[m.parent_id] = m               #store each message as the child of the message in its parent_id

    #walk the path from the root to the last child
    walk = []                                   #the ordered thread we are going to return
    previous = root[0]                          #start from the first parent, the root
    walk.append(previous)                       #append it to the list
    while True:                                 #as long as the current message has a child
        child = path.get(previous.id)           #look for its child (None if it is the last one)
        if child is None:
            break                               #no child: we reached the end of the thread
        walk.append(child)                      #append its child
        previous = child                        #the child becomes the parent

    if len(walk) != len(result):                #some message was never reached from the root (missing parent, detached cycle)
        raise InvariantError("inconsistent walk of the branch")

    return walk                                 #messages ordered from the root to the current end


def open_branch(anchor: Message, start: int, end: int, *, new_id: int, created_at: datetime,) -> Branch:
    """Create an open branch anchored to ``anchor.content[start:end]``.

    The selected text is copied into ``anchor_quote``. Per DESIGN.md the anchor
    must be an assistant message on main (depth = 1, no branches of branches).

    Raises:
        InvariantError: if the anchor or the offsets are not valid.
    """
    #check that everything is fine
    if anchor.role != Role.ASSISTANT:               #LIMIT: branches only on answers of the model
        raise InvariantError(f"message:{anchor.id} is not a response of the model")

    if anchor.branch_id is not None:                #LIMIT: depth 1 only, no branch of a branch
        raise InvariantError(f"message:{anchor.id} is not in main, but in {anchor.branch_id}")

    if not (0 <= start < end <= len(anchor.content)):   #non-empty selection inside the text; checked by hand because slicing never fails
        raise InvariantError(f"invalid selection [{start}:{end}]; message: {anchor.id} with {len(anchor.content)} characters")

    return Branch(                                  #a new object: the anchor itself is not modified
        id=new_id,                                  #id chosen by the caller (persistence)
        conversation_id= anchor.conversation_id,    #same conversation as the anchor
        anchor_message_id= anchor.id,               #the only link between the branch and main (§14.1)
        anchor_start= start,                        #offsets of the selection, in characters
        anchor_end= end,
        anchor_quote= anchor.content[start:end],    #copy of the selected text: it survives re-rendering
        status= BranchStatus.OPEN,                  #every branch starts open (§14.5)
        merge_message_id= None,                     #not merged yet
        created_at= created_at                      #timestamp chosen by the caller
    )


def merge_branch(branch: Branch, merge_message: Message, messages: Sequence[Message]) -> Branch:
    """Return ``branch`` marked as merged at ``merge_message`` (DESIGN.md §14.6).

    ``messages`` are all the messages of the conversation, and must already
    include ``merge_message``. The merge node is a ``merge`` message on main, in
    the branch's conversation, at the current end of main (merging anywhere else
    is out of scope for v1). Several branches may be merged at the same node.
    Take-away points are not checked: a merge with zero checked points is valid.

    Raises:
        InvariantError: if the branch is not open, the branch thread is empty,
            or the merge node is not valid.
    """
    if branch.status != BranchStatus.OPEN:                      #MERGED and DISCARDED are final: no second merge (§14.5)
        raise InvariantError(f"branch {branch.id} cannot be merged. is not OPEN but {branch.status}")
    if merge_message.role != Role.MERGE:                        #the node must be a merge message, not a user or assistant one
        raise InvariantError(f"message {merge_message.id} is not in role MERGE, but {merge_message.role}")
    if merge_message.branch_id is not None:                     #the merge node lives on main
        raise InvariantError(f"the message {merge_message.id} is not in Main branch")
    if merge_message.conversation_id != branch.conversation_id: #a node of another conversation is not accepted
        raise InvariantError(f"merge node {merge_message.id} is in conversation {merge_message.conversation_id}, branch {branch.id} in {branch.conversation_id}")

    #no merge of an empty list: thread returns [], and "not" catches it (§14.2)
    if not thread(messages, branch.id):
        raise InvariantError(f"thread is empty! branch: {branch.id}, message: {merge_message.id}")
    main = thread(messages)                                     #main in order, to know its current end
    if not main or main[-1].id != merge_message.id:             #compare with the last message to see if the node is the end of main
        last = main[-1].id if main else None                    #main can be empty: main[-1] would raise IndexError
        raise InvariantError(f"merge node {merge_message.id} is not the end of main (last message: {last})")
    return replace(branch, status=BranchStatus.MERGED, merge_message_id = merge_message.id )   #a copy with the two fields changed; the input stays as it was


def discard_branch(branch: Branch) -> Branch:
    """Return ``branch`` marked as discarded.

    A discarded branch never enters main's context.

    Raises:
        InvariantError: if the branch is not open.
    """
    #check that it is OPEN: no discard after a merge, no double discard (§14.5)
    if branch.status != BranchStatus.OPEN:
        raise InvariantError(f"error of status: branch {branch.id} is {branch.status}")

    #change the status of the branch and return it (a copy: the input stays as it was)
    return replace(branch, status=BranchStatus.DISCARDED)


def pending_branches(branches: Sequence[Branch]) -> list[Branch]:
    """Return the branches with no merge decision yet (drives the return-to-main banner).

    These are exactly the OPEN branches, in the order given: MERGED and
    DISCARDED are final states (DESIGN.md §14.5). Empty branches are included:
    they are still a pending decision, even if the only choice is to discard
    them (§14.8).
    """
    pending = []                                #new list: the input is never modified
    for b in branches:                          #go through the branches in the order given
        if b.status == BranchStatus.OPEN:       #open = no decision taken yet
            pending.append(b)                   #keep it, empty or not (§14.8)
    return pending


def check_invariants(
    messages: Sequence[Message],
    branches: Sequence[Branch],
    points: Sequence[TakeawayPoint],
) -> None:
    """Validate the whole state of one conversation.

    The other functions check one operation; this one checks everything that is
    stored, for example right after loading it or before committing a change.

    Messages:
    - ids are unique, and messages and branches all belong to one conversation;
    - a message's ``branch_id`` refers to an existing branch;
    - ``merge`` messages are on main only;
    - main and every branch thread form a single chain (see ``thread``).

    Branches:
    - ids are unique;
    - the anchor exists, is an assistant message on main (depth = 1), the
      offsets are inside it and ``anchor_quote`` is the selected text;
    - ``merge_message_id`` is set if and only if the branch is MERGED;
    - a merged branch points to a ``merge`` node on main, is not empty (§14.2),
      and its merge node comes after its anchor.

    Take-away points:
    - ids are unique, and a point's branch exists, whatever its status (§14.9);
    - positions are unique within a branch.

    Not checked here: "``text_generated`` is never overwritten". One snapshot
    cannot tell what a field contained before (§14.7).

    Raises:
        InvariantError: on the first violation found.
    """
    _check_unique_ids(messages, "message")          #first the ids: the checks below build dicts by id
    _check_unique_ids(branches, "branch")
    _check_unique_ids(points, "take-away point")
    #order: messages first, because the branch checks use threads that are already validated
    _check_messages(messages, branches)
    _check_branches(messages, branches)
    _check_points(branches, points)


def _check_unique_ids(items: Sequence[Message] | Sequence[Branch] | Sequence[TakeawayPoint], what: str) -> None:
    """Raise if two items share an id (a dict keyed by id would silently hide one)."""
    seen = set()                                    #ids met so far
    for item in items:
        if item.id in seen:                         #already met: duplicate
            raise InvariantError(f"duplicate {what} id {item.id}")
        seen.add(item.id)


def _check_messages(messages: Sequence[Message], branches: Sequence[Branch]) -> None:
    #the whole state belongs to a single conversation
    conversation_ids = set()                        #every conversation id that appears in the state
    for m in messages:
        conversation_ids.add(m.conversation_id)
    for b in branches:
        conversation_ids.add(b.conversation_id)
    if len(conversation_ids) > 1:                   #more than one: two conversations are mixed
        raise InvariantError(f"state mixes conversations {sorted(conversation_ids)}")

    branch_ids = set()                              #ids of the existing branches
    for b in branches:
        branch_ids.add(b.id)

    for m in messages:
        #orphan message: thread() would never see it, because nobody asks for that branch
        if m.branch_id is not None and m.branch_id not in branch_ids:
            raise InvariantError(f"message {m.id} is in branch {m.branch_id}, which does not exist")
        #merge nodes live on main only
        if m.role == Role.MERGE and m.branch_id is not None:
            raise InvariantError(f"merge node {m.id} is inside branch {m.branch_id}, not on main")

    #every thread is a single chain: thread() raises InvariantError if it is not
    thread(messages)                                #main
    for b in branches:
        thread(messages, b.id)                      #each branch


def _check_branches(messages: Sequence[Message], branches: Sequence[Branch]) -> None:
    by_id = {}                                      #message by id, to find anchors and merge nodes
    for m in messages:
        by_id[m.id] = m

    position = {}                                   #position of each main message, counted from the root
    for index, m in enumerate(thread(messages)):
        position[m.id] = index

    for b in branches:
        #--- anchor: the same rules as open_branch, checked again on the stored state
        anchor = by_id.get(b.anchor_message_id)
        if anchor is None:                          #the anchor must exist
            raise InvariantError(f"branch {b.id}: anchor message {b.anchor_message_id} does not exist")
        if anchor.branch_id is not None:            #depth 1: no branch of a branch
            raise InvariantError(f"branch {b.id}: anchor {anchor.id} is in branch {anchor.branch_id}, not on main")
        if anchor.role != Role.ASSISTANT:           #only answers of the model can be branched from
            raise InvariantError(f"branch {b.id}: anchor {anchor.id} is not an assistant message")
        if not (0 <= b.anchor_start < b.anchor_end <= len(anchor.content)):    #non-empty selection inside the text
            raise InvariantError(f"branch {b.id}: invalid selection [{b.anchor_start}:{b.anchor_end}] in message {anchor.id}")
        if anchor.content[b.anchor_start:b.anchor_end] != b.anchor_quote:      #the copy must match the selected text
            raise InvariantError(f"branch {b.id}: anchor_quote is not the selected text of message {anchor.id}")

        #--- status and merge node go together: MERGED <=> merge_message_id is set
        if b.status != BranchStatus.MERGED:
            if b.merge_message_id is not None:      #open or discarded, but pointing to a merge node
                raise InvariantError(f"branch {b.id} is {b.status} but has merge node {b.merge_message_id}")
            continue                                #OPEN or DISCARDED: nothing else to check

        if b.merge_message_id is None:              #merged, but no merge node
            raise InvariantError(f"branch {b.id} is merged but has no merge node")
        node = by_id.get(b.merge_message_id)
        if node is None:                            #the merge node must exist
            raise InvariantError(f"branch {b.id}: merge node {b.merge_message_id} does not exist")
        if node.role != Role.MERGE or node.branch_id is not None:   #a merge message, on main
            raise InvariantError(f"branch {b.id}: message {node.id} is not a merge node on main")
        if not thread(messages, b.id):              #an empty branch cannot be merged (§14.2)
            raise InvariantError(f"branch {b.id} is merged but has no messages")
        #a branch cannot come back into main before the point it started from
        if position[node.id] <= position[anchor.id]:
            raise InvariantError(f"branch {b.id}: merge node {node.id} comes before its anchor {anchor.id}")


def _check_points(branches: Sequence[Branch], points: Sequence[TakeawayPoint]) -> None:
    branch_ids = set()                              #ids of the existing branches
    for b in branches:
        branch_ids.add(b.id)

    used = set()                                    #(branch, position) pairs already seen
    for p in points:
        #the branch must exist, whatever its status (§14.9)
        if p.branch_id not in branch_ids:
            raise InvariantError(f"take-away point {p.id} is in branch {p.branch_id}, which does not exist")
        #two points at the same position would make the order of the checklist ambiguous
        if (p.branch_id, p.position) in used:
            raise InvariantError(f"branch {p.branch_id} has two take-away points at position {p.position}")
        used.add((p.branch_id, p.position))
