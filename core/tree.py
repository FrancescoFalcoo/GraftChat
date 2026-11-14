"""Operations and invariants on the conversation tree (DESIGN.md §5-§6).

Pure functions over ``core.models`` objects. Ids and timestamps are supplied
by the caller (assigned by persistence, which lives outside ``core``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from core.models import Branch, Message, TakeawayPoint, BranchStatus, Role


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
