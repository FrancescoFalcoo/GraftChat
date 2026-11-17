"""SQLite persistence: connection, migrations and the queries the API needs.

Rows are converted to and from the ``core.models`` dataclasses, which mirror
the tables one-to-one (DESIGN.md §6). No tree rule is decided here: this module
only stores what ``core.tree`` returns.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.models import (
    Branch,
    BranchStatus,
    CallPurpose,
    Condition,
    Conversation,
    LLMCallLog,
    Message,
    Role,
    TakeawayPoint,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


# --- connection and migrations ---------------------------------------------------


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the database (creating the file and its folder if needed) and migrate it."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: no implicit transactions, see transaction() below.
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def _migrations() -> list[tuple[int, Path]]:
    found = []
    for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        found.append((int(file.name.split("_", 1)[0]), file))
    return found


def migrate(conn: sqlite3.Connection) -> int:
    """Apply the pending migrations in order. Returns the resulting schema version.

    The version is kept in ``PRAGMA user_version``. Each file
    ``migrations/NNNN_name.sql`` is applied once, in its own transaction.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, file in _migrations():
        if number <= current:
            continue
        sql = file.read_text(encoding="utf-8")
        try:
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        current = number
    return current


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a write transaction: commit on success, roll back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# --- row <-> dataclass --------------------------------------------------------------


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(id=row["id"], title=row["title"], created_at=_dt(row["created_at"]))


def _message(row: sqlite3.Row) -> Message:
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        branch_id=row["branch_id"],
        parent_id=row["parent_id"],
        role=Role(row["role"]),
        content=row["content"],
        created_at=_dt(row["created_at"]),
    )


def _branch(row: sqlite3.Row) -> Branch:
    return Branch(
        id=row["id"],
        conversation_id=row["conversation_id"],
        anchor_message_id=row["anchor_message_id"],
        anchor_start=row["anchor_start"],
        anchor_end=row["anchor_end"],
        anchor_quote=row["anchor_quote"],
        status=BranchStatus(row["status"]),
        merge_message_id=row["merge_message_id"],
        created_at=_dt(row["created_at"]),
        base_message_id=row["base_message_id"],
    )


def _point(row: sqlite3.Row) -> TakeawayPoint:
    return TakeawayPoint(
        id=row["id"],
        branch_id=row["branch_id"],
        position=row["position"],
        title=row["title"],
        text_generated=row["text_generated"],
        text_final=row["text_final"],
        included=bool(row["included"]),
    )


def _log(row: sqlite3.Row) -> LLMCallLog:
    return LLMCallLog(
        id=row["id"],
        conversation_id=row["conversation_id"],
        branch_id=row["branch_id"],
        purpose=CallPurpose(row["purpose"]),
        condition=Condition(row["condition"]) if row["condition"] else None,
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost_estimate=row["cost_estimate"],
        prompt_json=row["prompt_json"],
        response_text=row["response_text"],
        created_at=_dt(row["created_at"]),
    )


# --- conversations ---------------------------------------------------------------------


def create_conversation(conn: sqlite3.Connection, title: str, now: datetime) -> Conversation:
    cur = conn.execute(
        "INSERT INTO conversation (title, created_at) VALUES (?, ?)", (title, now.isoformat())
    )
    return Conversation(id=cur.lastrowid, title=title, created_at=now)


def get_conversation(conn: sqlite3.Connection, conversation_id: int) -> Conversation | None:
    row = conn.execute("SELECT * FROM conversation WHERE id = ?", (conversation_id,)).fetchone()
    return _conversation(row) if row else None


def rename_conversation(conn: sqlite3.Connection, conversation_id: int, title: str) -> None:
    conn.execute("UPDATE conversation SET title = ? WHERE id = ?", (title, conversation_id))


def list_conversations(conn: sqlite3.Connection) -> list[tuple[Conversation, int]]:
    """Every conversation with its number of open branches, newest first."""
    rows = conn.execute(
        """
        SELECT c.*, (SELECT COUNT(*) FROM branch b
                     WHERE b.conversation_id = c.id AND b.status = 'open') AS open_branches
        FROM conversation c
        ORDER BY c.created_at DESC, c.id DESC
        """
    ).fetchall()
    return [(_conversation(row), row["open_branches"]) for row in rows]


# --- the state of one conversation, as core sees it ---------------------------------------


def load_messages(conn: sqlite3.Connection, conversation_id: int) -> list[Message]:
    rows = conn.execute(
        "SELECT * FROM message WHERE conversation_id = ? ORDER BY id", (conversation_id,)
    ).fetchall()
    return [_message(row) for row in rows]


def load_branches(conn: sqlite3.Connection, conversation_id: int) -> list[Branch]:
    rows = conn.execute(
        "SELECT * FROM branch WHERE conversation_id = ? ORDER BY created_at, id",
        (conversation_id,),
    ).fetchall()
    return [_branch(row) for row in rows]


def load_points(conn: sqlite3.Connection, conversation_id: int) -> list[TakeawayPoint]:
    rows = conn.execute(
        """
        SELECT p.* FROM takeaway_point p JOIN branch b ON b.id = p.branch_id
        WHERE b.conversation_id = ?
        ORDER BY p.branch_id, p.position
        """,
        (conversation_id,),
    ).fetchall()
    return [_point(row) for row in rows]


def load_state(
    conn: sqlite3.Connection, conversation_id: int
) -> tuple[list[Message], list[Branch], list[TakeawayPoint]]:
    """Messages, branches and take-away points of one conversation."""
    return (
        load_messages(conn, conversation_id),
        load_branches(conn, conversation_id),
        load_points(conn, conversation_id),
    )


# --- messages -----------------------------------------------------------------------------


def get_message(conn: sqlite3.Connection, message_id: int) -> Message | None:
    row = conn.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
    return _message(row) if row else None


def insert_message(
    conn: sqlite3.Connection,
    *,
    conversation_id: int,
    branch_id: int | None,
    parent_id: int | None,
    role: Role,
    content: str,
    now: datetime,
) -> Message:
    cur = conn.execute(
        """
        INSERT INTO message (conversation_id, branch_id, parent_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, branch_id, parent_id, role.value, content, now.isoformat()),
    )
    return Message(
        id=cur.lastrowid,
        conversation_id=conversation_id,
        branch_id=branch_id,
        parent_id=parent_id,
        role=role,
        content=content,
        created_at=now,
    )


def delete_message(conn: sqlite3.Connection, message_id: int) -> None:
    conn.execute("DELETE FROM message WHERE id = ?", (message_id,))


# --- branches -----------------------------------------------------------------------------


def get_branch(conn: sqlite3.Connection, branch_id: int) -> Branch | None:
    row = conn.execute("SELECT * FROM branch WHERE id = ?", (branch_id,)).fetchone()
    return _branch(row) if row else None


def next_branch_id(conn: sqlite3.Connection) -> int:
    """The id the next branch will get. Call it inside a transaction.

    ``core.tree.open_branch`` takes the new id as an argument, so the id has to
    be known before the row exists.
    """
    return conn.execute("SELECT IFNULL(MAX(id), 0) + 1 FROM branch").fetchone()[0]


def insert_branch(conn: sqlite3.Connection, branch: Branch) -> None:
    conn.execute(
        """
        INSERT INTO branch (id, conversation_id, anchor_message_id, anchor_start, anchor_end,
                            anchor_quote, status, merge_message_id, created_at,
                            base_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            branch.id,
            branch.conversation_id,
            branch.anchor_message_id,
            branch.anchor_start,
            branch.anchor_end,
            branch.anchor_quote,
            branch.status.value,
            branch.merge_message_id,
            branch.created_at.isoformat(),
            branch.base_message_id,
        ),
    )


def update_branch_status(conn: sqlite3.Connection, branch: Branch) -> None:
    """Store the status and merge node of a branch returned by ``core.tree``."""
    conn.execute(
        "UPDATE branch SET status = ?, merge_message_id = ? WHERE id = ?",
        (branch.status.value, branch.merge_message_id, branch.id),
    )


# --- attachments --------------------------------------------------------------------------


@dataclass(frozen=True)
class Attachment:
    """An image attached to a user message (not part of ``core``: the model input
    ``core.context`` builds is text; the API adds the images of each message)."""

    id: int
    message_id: int
    position: int
    kind: str
    mime: str
    name: str
    size: int


def _attachment(row: sqlite3.Row) -> Attachment:
    return Attachment(
        id=row["id"],
        message_id=row["message_id"],
        position=row["position"],
        kind=row["kind"],
        mime=row["mime"],
        name=row["name"],
        size=row["size"],
    )


def insert_attachment(
    conn: sqlite3.Connection,
    *,
    message_id: int,
    position: int,
    mime: str,
    name: str,
    data: bytes,
    now: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO attachment (message_id, position, kind, mime, name, size, data, created_at)
        VALUES (?, ?, 'image', ?, ?, ?, ?, ?)
        """,
        (message_id, position, mime, name, len(data), data, now.isoformat()),
    )


def load_attachments(conn: sqlite3.Connection, conversation_id: int) -> dict[int, list[Attachment]]:
    """The attachments of one conversation, by message id, in position order (no bytes)."""
    rows = conn.execute(
        """
        SELECT a.id, a.message_id, a.position, a.kind, a.mime, a.name, a.size
        FROM attachment a JOIN message m ON m.id = a.message_id
        WHERE m.conversation_id = ?
        ORDER BY a.message_id, a.position
        """,
        (conversation_id,),
    ).fetchall()
    found: dict[int, list[Attachment]] = {}
    for row in rows:
        found.setdefault(row["message_id"], []).append(_attachment(row))
    return found


def attachment_data(conn: sqlite3.Connection, attachment_id: int) -> tuple[Attachment, bytes] | None:
    row = conn.execute("SELECT * FROM attachment WHERE id = ?", (attachment_id,)).fetchone()
    return (_attachment(row), bytes(row["data"])) if row else None


# --- take-away points ---------------------------------------------------------------------


def get_point(conn: sqlite3.Connection, point_id: int) -> TakeawayPoint | None:
    row = conn.execute("SELECT * FROM takeaway_point WHERE id = ?", (point_id,)).fetchone()
    return _point(row) if row else None


def branch_points(conn: sqlite3.Connection, branch_id: int) -> list[TakeawayPoint]:
    rows = conn.execute(
        "SELECT * FROM takeaway_point WHERE branch_id = ? ORDER BY position", (branch_id,)
    ).fetchall()
    return [_point(row) for row in rows]


def replace_points(
    conn: sqlite3.Connection, branch_id: int, items: Sequence[tuple[str, str]]
) -> list[TakeawayPoint]:
    """Replace a branch's points with freshly generated ``(title, text)`` pairs.

    New points are all included (DESIGN.md §8) and ``text_final`` starts equal
    to ``text_generated``.
    """
    conn.execute("DELETE FROM takeaway_point WHERE branch_id = ?", (branch_id,))
    for position, (title, text) in enumerate(items):
        conn.execute(
            """
            INSERT INTO takeaway_point (branch_id, position, title, text_generated, text_final,
                                        included)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (branch_id, position, title, text, text),
        )
    return branch_points(conn, branch_id)


def update_point(
    conn: sqlite3.Connection,
    point_id: int,
    *,
    included: bool | None = None,
    text_final: str | None = None,
) -> None:
    """Change the checkbox and/or the final text. ``text_generated`` is never touched."""
    if included is not None:
        conn.execute(
            "UPDATE takeaway_point SET included = ? WHERE id = ?", (int(included), point_id)
        )
    if text_final is not None:
        conn.execute(
            "UPDATE takeaway_point SET text_final = ? WHERE id = ?", (text_final, point_id)
        )


# --- LLM call log -------------------------------------------------------------------------


def insert_log(
    conn: sqlite3.Connection,
    *,
    conversation_id: int,
    branch_id: int | None,
    purpose: CallPurpose,
    condition: Condition | None = None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_estimate: float,
    prompt_json: str,
    response_text: str,
    now: datetime,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO llm_call_log (conversation_id, branch_id, purpose, condition, model,
                                  input_tokens, output_tokens, cost_estimate, prompt_json,
                                  response_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            branch_id,
            purpose.value,
            condition.value if condition else None,
            model,
            input_tokens,
            output_tokens,
            cost_estimate,
            prompt_json,
            response_text,
            now.isoformat(),
        ),
    )
    return cur.lastrowid


def list_logs(conn: sqlite3.Connection, conversation_id: int | None = None) -> list[LLMCallLog]:
    if conversation_id is None:
        rows = conn.execute("SELECT * FROM llm_call_log ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM llm_call_log WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
    return [_log(row) for row in rows]


def month_spend(conn: sqlite3.Connection, now: datetime) -> float:
    """Sum of ``cost_estimate`` over the calendar month of ``now`` (same timezone as stored)."""
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    row = conn.execute(
        "SELECT IFNULL(SUM(cost_estimate), 0.0) FROM llm_call_log WHERE created_at >= ?",
        (start.isoformat(),),
    ).fetchone()
    return float(row[0])
