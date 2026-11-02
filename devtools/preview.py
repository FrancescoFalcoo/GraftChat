"""Live preview of core/ on a sample conversation.

Dev tool, not part of core/ and not a test: it calls every core function on a
fixed sample state and prints whatever comes back, so each change to core/ is
visible as soon as the file is saved. It holds no expected results.

    python devtools/preview.py                              # run once
    watchfiles "python devtools/preview.py" core devtools   # re-run on every save
"""

from __future__ import annotations

import copy
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(errors="replace")

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

ANSWER = (
    "Quattro interventi, in ordine di impatto:\n"
    "1. Comprimi le immagini e servile in WebP o AVIF.\n"
    "2. Abilita la cache HTTP per i file statici.\n"
    "3. Rimuovi il JavaScript che non usi.\n"
    "4. Usa una CDN vicina ai tuoi utenti."
)
QUOTES = {
    1: "Comprimi le immagini e servile in WebP o AVIF",
    2: "Abilita la cache HTTP per i file statici",
    3: "Usa una CDN vicina ai tuoi utenti",
}
NEW_QUOTE = "Rimuovi il JavaScript che non usi"


@dataclass
class Sample:
    messages: list
    branches: list
    points: list


def build_sample(models) -> Sample:
    """Stored state of one conversation, as it would come out of SQLite.

    Main: question -> 4-point answer -> merge node (branch 1) -> follow-up.
    Branch 1 merged, branch 2 still open, branch 3 discarded.
    """
    Role, Status = models.Role, models.BranchStatus
    t0 = datetime(2026, 11, 2, 10, 0)

    def msg(mid, branch_id, parent_id, role, content):
        return models.Message(
            id=mid, conversation_id=1, branch_id=branch_id, parent_id=parent_id,
            role=role, content=content, created_at=t0 + timedelta(minutes=mid),
        )

    def branch(bid, status, merge_message_id=None):
        quote = QUOTES[bid]
        start = ANSWER.index(quote)
        return models.Branch(
            id=bid, conversation_id=1, anchor_message_id=2,
            anchor_start=start, anchor_end=start + len(quote), anchor_quote=quote,
            status=status, merge_message_id=merge_message_id,
            created_at=t0 + timedelta(minutes=2, seconds=bid),
        )

    def point(pid, branch_id, position, title, generated, *, final=None, included=True):
        return models.TakeawayPoint(
            id=pid, branch_id=branch_id, position=position, title=title,
            text_generated=generated,
            text_final=generated if final is None else final,
            included=included,
        )

    messages = [
        msg(1, None, None, Role.USER, "Come rendo più veloce il mio sito?"),
        msg(2, None, 1, Role.ASSISTANT, ANSWER),
        msg(3, 1, None, Role.USER, "Meglio WebP o AVIF?"),
        msg(4, 1, 3, Role.ASSISTANT,
            "AVIF comprime di più a parità di qualità; WebP è supportato ovunque. "
            "Usa AVIF con WebP come fallback tramite <picture>."),
        msg(5, 2, None, Role.USER, "Quali header devo impostare?"),
        msg(6, 2, 5, Role.ASSISTANT,
            "Cache-Control: public, max-age=31536000, immutable per i file con hash nel nome."),
        msg(7, 3, None, Role.USER, "Cos'è una CDN?"),
        msg(8, 3, 7, Role.ASSISTANT,
            "Una rete di server distribuiti che servono i tuoi file dal nodo più vicino all'utente."),
        msg(9, None, 2, Role.MERGE, ""),
        msg(10, None, 9, Role.USER, "Ok, cosa faccio per prima cosa con le immagini?"),
    ]
    branches = [
        branch(1, Status.MERGED, merge_message_id=9),
        branch(2, Status.OPEN),
        branch(3, Status.DISCARDED),
    ]
    points = [
        point(1, 1, 1, "AVIF per le foto",
              "Usa AVIF per le foto: a parità di qualità pesa meno di WebP."),
        point(2, 1, 2, "WebP come fallback",
              "Servi WebP come fallback con l'elemento <picture>.",
              final="Fallback WebP via <picture> per i browser senza AVIF."),
        point(3, 1, 3, "Conversione in batch",
              "Converti le immagini in batch con Squoosh o sharp.", included=False),
        point(4, 3, 1, "CDN = server vicini",
              "Una CDN serve i file dal nodo più vicino all'utente."),
    ]
    return Sample(messages, branches, points)


def sections(models, tree, context, sample: Sample) -> list[tuple[str, Callable[[], object]]]:
    """Every core call to preview, each on a fresh copy of the sample."""

    def fresh() -> Sample:
        return copy.deepcopy(sample)

    def by_id(items, item_id):
        return next(item for item in items if item.id == item_id)

    def open_new_branch():
        s = fresh()
        start = ANSWER.index(NEW_QUOTE)
        return tree.open_branch(
            by_id(s.messages, 2), start, start + len(NEW_QUOTE),
            new_id=4, created_at=datetime(2026, 11, 2, 11, 0),
        )

    def merge_open_branch():
        s = fresh()
        merge_node = models.Message(
            id=11, conversation_id=1, branch_id=None, parent_id=10,
            role=models.Role.MERGE, content="", created_at=datetime(2026, 11, 2, 11, 0),
        )
        return tree.merge_branch(by_id(s.branches, 2), merge_node)

    def branch_context(bid):
        s = fresh()
        return context.build_branch_context(by_id(s.branches, bid), s.messages, s.branches, s.points)

    return [
        ("tree.thread(main)", lambda: tree.thread(fresh().messages)),
        *[
            (f"tree.thread(branch {bid})", lambda bid=bid: tree.thread(fresh().messages, bid))
            for bid in QUOTES
        ],
        (f"tree.open_branch on «{NEW_QUOTE}»", open_new_branch),
        ("tree.merge_branch(branch 2) at a new merge node #11", merge_open_branch),
        ("tree.discard_branch(branch 2)", lambda: tree.discard_branch(by_id(fresh().branches, 2))),
        ("tree.pending_branches", lambda: tree.pending_branches(fresh().branches)),
        ("tree.check_invariants (sample state)",
         lambda: tree.check_invariants(fresh().messages, fresh().branches, fresh().points)),
        ("context.render_anchor_note(branch 2)",
         lambda: context.render_anchor_note(QUOTES[2])),
        ("context.render_merge_block(branch 1)",
         lambda: context.render_merge_block(
             QUOTES[1], [p for p in fresh().points if p.branch_id == 1])),
        ("context.build_main_context",
         lambda: context.build_main_context(fresh().messages, fresh().branches, fresh().points)),
        *[
            (f"context.build_branch_context(branch {bid})", lambda bid=bid: branch_context(bid))
            for bid in QUOTES
        ],
    ]


def show(value, indent: str = "  ") -> str:
    """Readable rendering of whatever core returns."""
    name = type(value).__name__
    if value is None:
        return f"{indent}{DIM}None{RESET}"
    if isinstance(value, str):
        return "\n".join(f"{indent}{line}" for line in (value.splitlines() or ['""']))
    if isinstance(value, (list, tuple)):
        return "\n".join(show(v, indent) for v in value) if value else f"{indent}[]"
    if name == "Context" and hasattr(value, "messages"):
        return f"{indent}{DIM}{len(value.messages)} messages{RESET}\n" + show(value.messages, indent)
    if name == "ContextMessage":
        return f"{indent}{BOLD}[{value.role}]{RESET}\n" + show(value.content, indent + "    ")
    if name == "Message":
        thread = "main" if value.branch_id is None else f"branch {value.branch_id}"
        text = value.content.replace("\n", " ")
        text = text if len(text) <= 60 else text[:57] + "..."
        return f"{indent}#{value.id} {thread} {value.role} (parent {value.parent_id}): {text}"
    if name == "Branch":
        return (f"{indent}branch {value.id} [{value.status}] «{value.anchor_quote}» "
                f"chars {value.anchor_start}-{value.anchor_end}, merge node {value.merge_message_id}")
    if name == "TakeawayPoint":
        box = "[x]" if value.included else "[ ]"
        edited = "" if value.text_final == value.text_generated else f" {DIM}(edited){RESET}"
        return f"{indent}{box} branch {value.branch_id} #{value.position} {value.title}: {value.text_final}{edited}"
    if is_dataclass(value):
        return "\n".join(f"{indent}{f.name} = {getattr(value, f.name)!r}" for f in fields(value))
    return f"{indent}{value!r}"


def print_error(exc: BaseException) -> None:
    print(f"  {RED}{type(exc).__name__}: {exc}{RESET}")
    frames = traceback.extract_tb(exc.__traceback__)
    in_core = [f for f in frames if "core" in Path(f.filename).parts] or frames[-1:]
    for frame in in_core:
        print(f"  {DIM}{Path(frame.filename).name}:{frame.lineno} in {frame.name}: {frame.line}{RESET}")


def run(title: str, call: Callable[[], object]) -> str:
    print(f"\n{BOLD}{CYAN}{title}{RESET}")
    try:
        result = call()
    except NotImplementedError:
        print(f"  {YELLOW}da implementare{RESET}")
        return "todo"
    except Exception as exc:
        print_error(exc)
        return "error"
    print(show(result))
    return "ok"


def main() -> int:
    if sys.stdout.isatty():
        print("\033[2J\033[3J\033[H", end="")
    print(f"{BOLD}GraftChat core preview{RESET}  {DIM}{datetime.now():%H:%M:%S}{RESET}")

    try:
        import core.context as context
        import core.models as models
        import core.tree as tree
    except Exception as exc:
        print(f"\n{RED}core/ non si importa{RESET}")
        print_error(exc)
        return 1

    try:
        sample = build_sample(models)
    except Exception as exc:
        print(f"\n{RED}Il campione non corrisponde più a core/models.py: aggiorna build_sample{RESET}")
        print_error(exc)
        return 1

    print(f"\n{BOLD}Stato di esempio (input){RESET}")
    print(show(sample.messages))
    print(show(sample.branches))
    print(show(sample.points))

    results = [run(title, call) for title, call in sections(models, tree, context, sample)]
    ok, todo, err = (results.count(s) for s in ("ok", "todo", "error"))
    print(f"\n{BOLD}Funzioni che rispondono: {GREEN}{ok}{RESET}{BOLD}/{len(results)}{RESET}"
          f"   {YELLOW}da implementare: {todo}{RESET}   {RED}errori: {err}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
