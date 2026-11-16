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
    result = []                                 #lista vuota dove appendiamo i messaggi di quel branch
    root = []

    #creazione lista dei messaggi
    for m in messages:                          #scorri tutti i messaggi nel "messages" (nella firma abbiamo ribattezzato la sequenza di messaggi in messages)
        if m.branch_id==branch_id:              #a differenza di java qui non servono i getter
            result.append(m)                    #nella nostra lista mettiamo tutti i messaggi di questo branch   
    if len(result)== 0:
        return []                               #ritorna la lista vuota se il branch è vuoto 

    #ricerca radice
    for m in result:
        if m.parent_id is None:                 #tra questi, cerchiamo il primo nodo del branch
            root.append(m)

    if len(root)!= 1:
        raise InvariantError(f"expected 1 root, found {len(root)}")

    #creazione dizionario, non importa l'ordine, l'importante è averli tutti legati padre e figlio
    path = {}                                   #dizionario dove si ricostruisce la sequenza di messaggi
    for m in result:
        if m.parent_id is not None:             
            if m.parent_id in path:
                raise InvariantError(f"two messages have parent {m.parent_id}")
            path[m.parent_id] = m               #scorro i messaggi e metto ogni messaggio come figlio di quello che ha scritto nel parent id
            
    #percorriamo il path da root all'ultimo figlio  
    walk = []      
    previous = root[0]                          #prendo il primo padre
    walk.append(previous)                       #appendo alla lista
    while True:                                 #finché il messaggio corrente ha un figlio
        child = path.get(previous.id)           #cerco il figlio (None se è l'ultimo)
        if child is None:
            break
        walk.append(child)                      #append di suo figlio
        previous = child                        #il figlio diventa il padre

    if len(walk) != len(result):
        raise InvariantError("inconsistent walk of the branch")
    
    return walk           


def open_branch(anchor: Message, start: int, end: int, *, new_id: int, created_at: datetime,) -> Branch:
    """Create an open branch anchored to ``anchor.content[start:end]``.

    The selected text is copied into ``anchor_quote``. Per DESIGN.md the anchor
    must be an assistant message on main (depth = 1, no branches of branches).

    Raises:
        InvariantError: if the anchor or the offsets are not valid.
    """
    #controlli che vada tutto bene
    if anchor.role != Role.ASSISTANT:               #LIMITE: solo branch su risposte del modello
        raise InvariantError(f"message:{anchor.id} is not a response of the model")

    if anchor.branch_id is not None:                #LIMITE: solo profondità 1 
        raise InvariantError(f"message:{anchor.id} is not in main, but in {anchor.branch_id}")
    
    if not (0 <= start < end <= len(anchor.content)):
        raise InvariantError(f"invalid selection [{start}:{end}]; message: {anchor.id} with {len(anchor.content)} characters")

    return Branch(
        id=new_id,
        conversation_id= anchor.conversation_id,
        anchor_message_id= anchor.id,
        anchor_start= start,
        anchor_end= end,
        anchor_quote= anchor.content[start:end],
        status= BranchStatus.OPEN,
        merge_message_id= None,
        created_at= created_at
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
    if branch.status != BranchStatus.OPEN:
        raise InvariantError(f"branch {branch.id} cannot be merged. is not OPEN but {branch.status}")
    if merge_message.role != Role.MERGE:
        raise InvariantError(f"message {merge_message.id} is not in role MERGE, but {merge_message.role}")
    if merge_message.branch_id is not None:
        raise InvariantError(f"the message {merge_message.id} is not in Main branch")
    if merge_message.conversation_id != branch.conversation_id:
        raise InvariantError(f"merge node {merge_message.id} is in conversation {merge_message.conversation_id}, branch {branch.id} in {branch.conversation_id}")
    
    #no merge di una lista vuota: thread restituisce [], con "not" è controllato
    if not thread(messages, branch.id):
        raise InvariantError(f"thread is empty! branch: {branch.id}, message: {merge_message.id}")
    main = thread(messages)
    if not main or main[-1].id != merge_message.id:             #confronto di ultimo messaggio per vedere se appartiene
        last = main[-1].id if main else None                    #main può essere vuoto: main[-1] darebbe IndexError
        raise InvariantError(f"merge node {merge_message.id} is not the end of main (last message: {last})")
    return replace(branch, status=BranchStatus.MERGED, merge_message_id = merge_message.id )


def discard_branch(branch: Branch) -> Branch:
    """Return ``branch`` marked as discarded.

    A discarded branch never enters main's context.

    Raises:
        InvariantError: if the branch is not open.
    """
    #controllo se OPEN
    if branch.status != BranchStatus.OPEN:                                                    
        raise InvariantError(f"error of status: branch {branch.id} is {branch.status}")

    #cambio lo stato del branch e lo restituisco
    return replace(branch, status=BranchStatus.DISCARDED)


def pending_branches(branches: Sequence[Branch]) -> list[Branch]:
    """Return the branches with no merge decision yet (drives the return-to-main banner).

    These are exactly the OPEN branches, in the order given: MERGED and
    DISCARDED are final states (DESIGN.md §14.5). Empty branches are included:
    they are still a pending decision, even if the only choice is to discard
    them (§14.8).
    """
    pending = []
    for b in branches:
        if b.status == BranchStatus.OPEN:
            pending.append(b)
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
    _check_unique_ids(messages, "message")
    _check_unique_ids(branches, "branch")
    _check_unique_ids(points, "take-away point")
    #ordine: prima i messaggi, perché i controlli sui branch usano i thread già validati
    _check_messages(messages, branches)
    _check_branches(messages, branches)
    _check_points(branches, points)


def _check_unique_ids(items: Sequence[Message] | Sequence[Branch] | Sequence[TakeawayPoint], what: str) -> None:
    """Raise if two items share an id (a dict keyed by id would silently hide one)."""
    seen = set()
    for item in items:
        if item.id in seen:
            raise InvariantError(f"duplicate {what} id {item.id}")
        seen.add(item.id)


def _check_messages(messages: Sequence[Message], branches: Sequence[Branch]) -> None:
    #tutto lo stato appartiene a una sola conversazione
    conversation_ids = set()
    for m in messages:
        conversation_ids.add(m.conversation_id)
    for b in branches:
        conversation_ids.add(b.conversation_id)
    if len(conversation_ids) > 1:
        raise InvariantError(f"state mixes conversations {sorted(conversation_ids)}")

    branch_ids = set()
    for b in branches:
        branch_ids.add(b.id)

    for m in messages:
        #messaggio orfano: thread() non lo vedrebbe mai, perché nessuno seleziona quel branch
        if m.branch_id is not None and m.branch_id not in branch_ids:
            raise InvariantError(f"message {m.id} is in branch {m.branch_id}, which does not exist")
        #i merge node stanno solo sul main
        if m.role == Role.MERGE and m.branch_id is not None:
            raise InvariantError(f"merge node {m.id} is inside branch {m.branch_id}, not on main")

    #ogni thread è una catena sola: thread() lancia InvariantError se non lo è
    thread(messages)
    for b in branches:
        thread(messages, b.id)


def _check_branches(messages: Sequence[Message], branches: Sequence[Branch]) -> None:
    by_id = {}                                      #messaggio per id, per trovare anchor e merge node
    for m in messages:
        by_id[m.id] = m

    position = {}                                   #posizione di ogni messaggio del main, dalla radice
    for index, m in enumerate(thread(messages)):
        position[m.id] = index

    for b in branches:
        #--- anchor: le stesse regole di open_branch
        anchor = by_id.get(b.anchor_message_id)
        if anchor is None:
            raise InvariantError(f"branch {b.id}: anchor message {b.anchor_message_id} does not exist")
        if anchor.branch_id is not None:            #profondità 1: niente branch di branch
            raise InvariantError(f"branch {b.id}: anchor {anchor.id} is in branch {anchor.branch_id}, not on main")
        if anchor.role != Role.ASSISTANT:
            raise InvariantError(f"branch {b.id}: anchor {anchor.id} is not an assistant message")
        if not (0 <= b.anchor_start < b.anchor_end <= len(anchor.content)):
            raise InvariantError(f"branch {b.id}: invalid selection [{b.anchor_start}:{b.anchor_end}] in message {anchor.id}")
        if anchor.content[b.anchor_start:b.anchor_end] != b.anchor_quote:
            raise InvariantError(f"branch {b.id}: anchor_quote is not the selected text of message {anchor.id}")

        #--- stato e merge node vanno insieme: MERGED <=> merge_message_id presente
        if b.status != BranchStatus.MERGED:
            if b.merge_message_id is not None:
                raise InvariantError(f"branch {b.id} is {b.status} but has merge node {b.merge_message_id}")
            continue                                #OPEN o DISCARDED: nient'altro da controllare

        if b.merge_message_id is None:
            raise InvariantError(f"branch {b.id} is merged but has no merge node")
        node = by_id.get(b.merge_message_id)
        if node is None:
            raise InvariantError(f"branch {b.id}: merge node {b.merge_message_id} does not exist")
        if node.role != Role.MERGE or node.branch_id is not None:
            raise InvariantError(f"branch {b.id}: message {node.id} is not a merge node on main")
        if not thread(messages, b.id):              #un branch vuoto non si può mergiare (§14.2)
            raise InvariantError(f"branch {b.id} is merged but has no messages")
        #un branch non può rientrare nel main prima del punto da cui è partito
        if position[node.id] <= position[anchor.id]:
            raise InvariantError(f"branch {b.id}: merge node {node.id} comes before its anchor {anchor.id}")


def _check_points(branches: Sequence[Branch], points: Sequence[TakeawayPoint]) -> None:
    branch_ids = set()
    for b in branches:
        branch_ids.add(b.id)

    used = set()                                    #coppie (branch, posizione) già viste
    for p in points:
        #il branch deve esistere, in qualunque stato sia (§14.9)
        if p.branch_id not in branch_ids:
            raise InvariantError(f"take-away point {p.id} is in branch {p.branch_id}, which does not exist")
        #due punti nella stessa posizione renderebbero ambiguo l'ordine della checklist
        if (p.branch_id, p.position) in used:
            raise InvariantError(f"branch {p.branch_id} has two take-away points at position {p.position}")
        used.add((p.branch_id, p.position))
