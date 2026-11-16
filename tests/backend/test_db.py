"""Tests for ``api.db``: migrations, round-trips to core dataclasses, schema constraints."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from api import db
from core.models import Branch, BranchStatus, CallPurpose, Role

NOW = datetime(2026, 11, 16, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


def add(conn, conversation_id, role, parent_id=None, branch_id=None, content="x"):
    return db.insert_message(
        conn,
        conversation_id=conversation_id,
        branch_id=branch_id,
        parent_id=parent_id,
        role=role,
        content=content,
        now=NOW,
    )


def make_branch(conn, conversation_id, anchor, branch_id=None):
    branch = Branch(
        id=branch_id or db.next_branch_id(conn),
        conversation_id=conversation_id,
        anchor_message_id=anchor.id,
        anchor_start=0,
        anchor_end=1,
        anchor_quote=anchor.content[0:1],
        status=BranchStatus.OPEN,
        merge_message_id=None,
        created_at=NOW,
    )
    db.insert_branch(conn, branch)
    return branch


def test_migrations_apply_once(tmp_path):
    path = tmp_path / "nested" / "g.db"
    first = db.connect(path)
    version = first.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(list(db.MIGRATIONS_DIR.glob("*.sql"))) >= 1
    first.close()
    second = db.connect(path)  # reopening must not re-run anything
    assert second.execute("PRAGMA user_version").fetchone()[0] == version
    second.close()


def test_state_round_trip(conn):
    conv = db.create_conversation(conn, "t", NOW)
    user = add(conn, conv.id, Role.USER, content="hi")
    answer = add(conn, conv.id, Role.ASSISTANT, parent_id=user.id, content="answer")
    branch = make_branch(conn, conv.id, answer)
    first = add(conn, conv.id, Role.USER, branch_id=branch.id, content="why?")
    points = db.replace_points(conn, branch.id, [("a", "text a"), ("b", "text b")])

    messages, branches, loaded_points = db.load_state(conn, conv.id)

    assert messages == [user, answer, first]
    assert branches == [branch]
    assert loaded_points == points
    assert [p.position for p in points] == [0, 1]
    assert all(p.included and p.text_final == p.text_generated for p in points)
    assert db.get_conversation(conn, conv.id) == conv
    assert db.get_message(conn, answer.id) == answer
    assert db.get_branch(conn, branch.id) == branch


def test_state_is_per_conversation(conn):
    one = db.create_conversation(conn, "one", NOW)
    two = db.create_conversation(conn, "two", NOW)
    add(conn, one.id, Role.USER)
    assert db.load_state(conn, two.id) == ([], [], [])


def test_list_conversations_newest_first_with_open_count(conn):
    old = db.create_conversation(conn, "old", NOW)
    new = db.create_conversation(conn, "new", NOW + timedelta(hours=1))
    user = add(conn, old.id, Role.USER)
    answer = add(conn, old.id, Role.ASSISTANT, parent_id=user.id)
    make_branch(conn, old.id, answer)
    discarded = make_branch(conn, old.id, answer)
    discarded.status = BranchStatus.DISCARDED
    db.update_branch_status(conn, discarded)

    assert [(c.id, n) for c, n in db.list_conversations(conn)] == [(new.id, 0), (old.id, 1)]


def test_update_point_never_touches_generated_text(conn):
    conv = db.create_conversation(conn, "t", NOW)
    user = add(conn, conv.id, Role.USER)
    answer = add(conn, conv.id, Role.ASSISTANT, parent_id=user.id)
    branch = make_branch(conn, conv.id, answer)
    (point,) = db.replace_points(conn, branch.id, [("title", "generated")])

    db.update_point(conn, point.id, included=False, text_final="edited")

    stored = db.get_point(conn, point.id)
    assert (stored.included, stored.text_final, stored.text_generated) == (
        False,
        "edited",
        "generated",
    )


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            db.create_conversation(conn, "lost", NOW)
            raise RuntimeError("boom")
    assert db.list_conversations(conn) == []


def test_schema_rejects_a_second_child_and_a_second_root(conn):
    conv = db.create_conversation(conn, "t", NOW)
    root = add(conn, conv.id, Role.USER)
    add(conn, conv.id, Role.ASSISTANT, parent_id=root.id)
    with pytest.raises(sqlite3.IntegrityError):
        add(conn, conv.id, Role.ASSISTANT, parent_id=root.id)  # fork
    with pytest.raises(sqlite3.IntegrityError):
        add(conn, conv.id, Role.USER)  # second root of main


def test_schema_rejects_merge_node_inside_a_branch(conn):
    conv = db.create_conversation(conn, "t", NOW)
    user = add(conn, conv.id, Role.USER)
    answer = add(conn, conv.id, Role.ASSISTANT, parent_id=user.id)
    branch = make_branch(conn, conv.id, answer)
    with pytest.raises(sqlite3.IntegrityError):
        add(conn, conv.id, Role.MERGE, branch_id=branch.id)


def test_schema_ties_merged_status_to_merge_node(conn):
    conv = db.create_conversation(conn, "t", NOW)
    user = add(conn, conv.id, Role.USER)
    answer = add(conn, conv.id, Role.ASSISTANT, parent_id=user.id)
    branch = make_branch(conn, conv.id, answer)
    branch.status = BranchStatus.MERGED  # merged, but no merge node
    with pytest.raises(sqlite3.IntegrityError):
        db.update_branch_status(conn, branch)


def test_month_spend_counts_only_the_current_month(conn):
    conv = db.create_conversation(conn, "t", NOW)

    def log(cost, when):
        db.insert_log(
            conn,
            conversation_id=conv.id,
            branch_id=None,
            purpose=CallPurpose.CHAT,
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_estimate=cost,
            prompt_json="[]",
            response_text="r",
            now=when,
        )

    log(0.25, NOW)
    log(0.5, NOW.replace(day=1, hour=0))
    log(9.0, NOW.replace(month=10, day=31, hour=23))  # previous month
    assert db.month_spend(conn, NOW) == pytest.approx(0.75)
    assert [entry.cost_estimate for entry in db.list_logs(conn, conv.id)] == [0.25, 0.5, 9.0]
