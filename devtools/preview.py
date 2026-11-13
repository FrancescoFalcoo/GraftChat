"""Preview of core/ on a sample conversation.

Dev tool, not part of core/ and not a test: it calls every core function on a
fixed sample state and reports whatever comes back, so each change to core/ is
visible as soon as the file is saved. It holds no expected results.

    python devtools/preview.py                              # run once, in the terminal
    watchfiles "python devtools/preview.py" core devtools   # re-run on every save
    python devtools/preview.py --json                       # machine output, used by live.py
"""

from __future__ import annotations

import copy
import json
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
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


@dataclass
class Section:
    group: str  # "tree" | "context"
    call: str  # function shown, e.g. "tree.thread"
    args: str  # short description of the arguments
    hint: str  # what the call is about, in plain words
    run: Callable[[], object]


@dataclass
class Outcome:
    section: Section
    status: str  # "ok" | "todo" | "error"
    value: object = None
    error: dict | None = field(default=None)


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


def sections(models, tree, context, sample: Sample) -> list[Section]:
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

    def main_context():
        s = fresh()
        return context.build_main_context(s.messages, s.branches, s.points)

    def check():
        s = fresh()
        return tree.check_invariants(s.messages, s.branches, s.points)

    return [
        Section("tree", "tree.thread", "main", "Messaggi di main, dalla radice alla fine",
                lambda: tree.thread(fresh().messages)),
        *[
            Section("tree", "tree.thread", f"branch {bid}", f"Messaggi del branch {bid}, in ordine",
                    lambda bid=bid: tree.thread(fresh().messages, bid))
            for bid in QUOTES
        ],
        Section("tree", "tree.open_branch", f"«{NEW_QUOTE}»",
                "Nuovo branch su un passaggio della risposta #2", open_new_branch),
        Section("tree", "tree.merge_branch", "branch 2, nodo #11",
                "Branch 2 dopo il merge in un nuovo nodo in coda a main", merge_open_branch),
        Section("tree", "tree.discard_branch", "branch 2", "Branch 2 dopo lo scarto",
                lambda: tree.discard_branch(by_id(fresh().branches, 2))),
        Section("tree", "tree.pending_branches", "tutti",
                "Branch senza decisione di merge (quelli del banner)",
                lambda: tree.pending_branches(fresh().branches)),
        Section("tree", "tree.check_invariants", "stato di esempio",
                "Validazione dell'intero stato: None = nessuna eccezione", check),
        Section("context", "context.render_anchor_note", "branch 2",
                "Nota che dice al modello di quale passaggio si parla",
                lambda: context.render_anchor_note(QUOTES[2])),
        Section("context", "context.render_merge_block", "branch 1",
                "Blocco inserito in main al nodo di merge del branch 1",
                lambda: context.render_merge_block(
                    QUOTES[1], [p for p in fresh().points if p.branch_id == 1])),
        Section("context", "context.build_main_context", "main",
                "Cosa riceve il modello alla prossima chiamata su main", main_context),
        *[
            Section("context", "context.build_branch_context", f"branch {bid}",
                    f"Cosa riceve il modello alla prossima chiamata nel branch {bid}",
                    lambda bid=bid: branch_context(bid))
            for bid in QUOTES
        ],
    ]


def error_info(exc: BaseException) -> dict:
    """Exception type, message and the frames inside core/ (or the last frame)."""
    frames = traceback.extract_tb(exc.__traceback__)
    in_core = [f for f in frames if "core" in Path(f.filename).parts] or frames[-1:]
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "frames": [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name, "code": f.line}
            for f in in_core
        ],
    }


def evaluate(section: Section) -> Outcome:
    try:
        value = section.run()
    except NotImplementedError:
        return Outcome(section, "todo")
    except Exception as exc:
        return Outcome(section, "error", error=error_info(exc))
    return Outcome(section, "ok", value=value)


def to_json(value):
    """Generic conversion of core objects (dataclasses, enums, datetimes) to JSON."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {"_type": type(value).__name__,
                **{f.name: to_json(getattr(value, f.name)) for f in fields(value)}}
    return {"_type": "repr", "repr": repr(value)}


def collect() -> dict:
    """Run everything and return the report as JSON-ready data."""
    report = {"generated_at": datetime.now().strftime("%H:%M:%S"),
              "fatal": None, "sample": None, "sections": []}
    try:
        import core.context as context
        import core.models as models
        import core.tree as tree
    except Exception as exc:
        report["fatal"] = {"title": "core/ non si importa", "error": error_info(exc)}
        return report
    try:
        sample = build_sample(models)
    except Exception as exc:
        report["fatal"] = {"title": "Il campione non corrisponde più a core/models.py: "
                                    "aggiorna build_sample in devtools/preview.py",
                           "error": error_info(exc)}
        return report

    report["sample"] = to_json({"messages": sample.messages, "branches": sample.branches,
                                "points": sample.points})
    for outcome in map(evaluate, sections(models, tree, context, sample)):
        s = outcome.section
        report["sections"].append({
            "group": s.group, "call": s.call, "args": s.args, "hint": s.hint,
            "status": outcome.status, "result": to_json(outcome.value), "error": outcome.error,
        })
    return report


# --- terminal output -------------------------------------------------------------


def show(value, indent: str = "  ") -> str:
    """Readable rendering of whatever core returns (JSON form)."""
    kind = value.get("_type") if isinstance(value, dict) else None
    if value is None:
        return f"{indent}{DIM}None{RESET}"
    if isinstance(value, str):
        return "\n".join(f"{indent}{line}" for line in (value.splitlines() or ['""']))
    if isinstance(value, list):
        return "\n".join(show(v, indent) for v in value) if value else f"{indent}[]"
    if kind == "Context":
        return f"{indent}{DIM}{len(value['messages'])} messages{RESET}\n" + show(value["messages"], indent)
    if kind == "ContextMessage":
        return f"{indent}{BOLD}[{value['role']}]{RESET}\n" + show(value["content"], indent + "    ")
    if kind == "Message":
        thread = "main" if value["branch_id"] is None else f"branch {value['branch_id']}"
        text = value["content"].replace("\n", " ")
        text = text if len(text) <= 60 else text[:57] + "..."
        return f"{indent}#{value['id']} {thread} {value['role']} (parent {value['parent_id']}): {text}"
    if kind == "Branch":
        return (f"{indent}branch {value['id']} [{value['status']}] «{value['anchor_quote']}» "
                f"chars {value['anchor_start']}-{value['anchor_end']}, "
                f"merge node {value['merge_message_id']}")
    if kind == "TakeawayPoint":
        box = "[x]" if value["included"] else "[ ]"
        edited = "" if value["text_final"] == value["text_generated"] else f" {DIM}(edited){RESET}"
        return (f"{indent}{box} branch {value['branch_id']} #{value['position']} "
                f"{value['title']}: {value['text_final']}{edited}")
    if kind == "repr":
        return f"{indent}{value['repr']}"
    if isinstance(value, dict):
        return "\n".join(f"{indent}{k} = {v!r}" for k, v in value.items() if k != "_type")
    return f"{indent}{value!r}"


def print_error(error: dict) -> None:
    print(f"  {RED}{error['type']}: {error['message']}{RESET}")
    for f in error["frames"]:
        print(f"  {DIM}{f['file']}:{f['line']} in {f['function']}: {f['code']}{RESET}")


def print_report(report: dict) -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[3J\033[H", end="")
    print(f"{BOLD}GraftChat core preview{RESET}  {DIM}{report['generated_at']}{RESET}")
    if report["fatal"]:
        print(f"\n{RED}{report['fatal']['title']}{RESET}")
        print_error(report["fatal"]["error"])
        return

    sample = report["sample"]
    print(f"\n{BOLD}Stato di esempio (input){RESET}")
    for key in ("messages", "branches", "points"):
        print(show(sample[key]))

    for s in report["sections"]:
        print(f"\n{BOLD}{CYAN}{s['call']}({s['args']}){RESET}")
        if s["status"] == "todo":
            print(f"  {YELLOW}da implementare{RESET}")
        elif s["status"] == "error":
            print_error(s["error"])
        else:
            print(show(s["result"]))

    statuses = [s["status"] for s in report["sections"]]
    ok, todo, err = (statuses.count(k) for k in ("ok", "todo", "error"))
    print(f"\n{BOLD}Funzioni che rispondono: {GREEN}{ok}{RESET}{BOLD}/{len(statuses)}{RESET}"
          f"   {YELLOW}da implementare: {todo}{RESET}   {RED}errori: {err}{RESET}")


def main() -> int:
    report = collect()
    if "--json" in sys.argv[1:]:
        sys.stdout.write(json.dumps(report, ensure_ascii=True))
    else:
        print_report(report)
    return 1 if report["fatal"] else 0


if __name__ == "__main__":
    sys.exit(main())
