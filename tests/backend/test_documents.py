"""Documents on user messages: text extraction (api/documents.py) and the API (DESIGN.md §14.13)."""

from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from api import db, documents
from api.documents import DocumentError, document_kind, extract_text, render_document

from api.provider import ModelInfo

from .conftest import TEST_MODEL
from .test_app import error_code, new_conversation, open_branch, say


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def make_pdf(*pages: str) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        )
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_docx(*paragraphs: str) -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


# --- extraction ---------------------------------------------------------------------------


def test_pdf_text_is_read_page_by_page():
    text = extract_text("pdf", "a.pdf", make_pdf("Hello world", "Second page"))
    assert text == "[page 1]\nHello world\n\n[page 2]\nSecond page"


def test_docx_paragraphs_are_read():
    assert extract_text("docx", "a.docx", make_docx("First", "Second")) == "First\nSecond"


@pytest.mark.parametrize(
    "data, expected",
    [(b"plain", "plain"), ("﻿bom è".encode("utf-8"), "bom è"), ("utf16".encode("utf-16"), "utf16")],
)
def test_plain_text_encodings(data, expected):
    assert extract_text("text", "a.txt", data) == expected


def test_kinds_come_from_the_bytes_and_the_extension():
    assert document_kind("anything.bin", make_pdf("x")) == "pdf"
    assert document_kind("a.docx", make_docx("x")) == "docx"
    assert document_kind("main.py", b"print(1)") == "text"
    assert document_kind("Dockerfile", b"FROM python") == "text"
    assert document_kind("photo.heic", b"\x00\x01") is None
    assert document_kind("archive.zip", b"PK\x03\x04") is None  # a zip that is not .docx


@pytest.mark.parametrize(
    "kind, name, data, fragment",
    [
        ("text", "a.txt", b"", "empty"),
        ("text", "a.txt", b"\x00\x01\x02", "binary"),
        ("text", "a.txt", b"\xff\xfa bad", "not UTF-8"),
        ("pdf", "a.pdf", b"%PDF-1.4 broken", "could not be read"),
        ("pdf", "a.pdf", make_pdf(""), "no text"),
        ("docx", "a.docx", b"PK\x03\x04 not a zip", "could not be read"),
        ("text", "big.txt", b"x" * (documents.MAX_DOCUMENT_CHARS + 1), "the limit is"),
    ],
)
def test_unreadable_documents_say_why(kind, name, data, fragment):
    with pytest.raises(DocumentError, match=fragment):
        extract_text(kind, name, data)


def test_rendered_block_names_the_document():
    assert render_document('my "notes".md', "body") == "<document name=\"my 'notes'.md\">\nbody\n</document>"


# --- API --------------------------------------------------------------------------------------


def send(client, conversation_id, content, files, branch_id=None):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": content, "branch_id": branch_id, "files": files},
    )


def test_document_text_is_sent_after_the_message_and_logged(client, provider, service):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "summarise this", [{"name": "report.pdf", "data": b64(make_pdf("Revenue grew"))}])
    assert response.status_code == 200, response.text
    (attachment,) = response.json()["main"][0]["attachments"]
    assert (attachment["kind"], attachment["mime"]) == ("document", "application/pdf")
    expected_text = "[page 1]\nRevenue grew"
    assert attachment["chars"] == len(expected_text)

    (sent,) = provider.calls[-1][1]
    assert sent.content == "summarise this\n\n" + render_document("report.pdf", expected_text)
    assert sent.images == ()
    with db.connect(service.config.db_path) as conn:
        (log,) = db.list_logs(conn, conversation_id)
    assert "Revenue grew" in json.loads(log.prompt_json)[0]["content"]  # the log holds the exact text


def test_documents_and_images_together(client, provider, service):
    service._models_fetcher = lambda: [ModelInfo(TEST_MODEL, "Chat", 8000, images=True)]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    conversation_id = new_conversation(client)
    files = [{"name": "notes.md", "data": b64(b"# Notes")}, {"name": "a.png", "data": b64(png)}]
    attachments = send(client, conversation_id, "", files).json()["main"][0]["attachments"]
    assert [a["kind"] for a in attachments] == ["document", "image"]
    (sent,) = provider.calls[-1][1]
    assert sent.content == render_document("notes.md", "# Notes") and len(sent.images) == 1


def test_documents_of_main_reach_a_branch_opened_after_them(client, provider):
    conversation_id = new_conversation(client)
    provider.queue.append("The plan has two phases.")
    state = send(client, conversation_id, "read", [{"name": "plan.txt", "data": b64(b"Phase one, phase two")}]).json()
    branch_id = open_branch(client, conversation_id, state["main"][-1], "two phases")
    say(client, conversation_id, "why two?", branch_id)
    assert "Phase one, phase two" in provider.calls[-1][1][0].content


def test_unreadable_document_is_refused_and_nothing_is_stored(client, provider):
    conversation_id = new_conversation(client)
    response = send(client, conversation_id, "read", [{"name": "scan.pdf", "data": b64(make_pdf(""))}])
    assert response.status_code == 422 and error_code(response) == "validation"
    assert "scanned" in response.json()["error"]["message"]
    assert client.get(f"/api/conversations/{conversation_id}").json()["main"] == []
    assert provider.calls == []


def test_documents_are_downloaded_never_rendered(client, provider):
    conversation_id = new_conversation(client)
    html = b"<script>alert(1)</script>"
    state = send(client, conversation_id, "x", [{"name": "page.html", "data": b64(html)}]).json()
    attachment_id = state["main"][0]["attachments"][0]["id"]
    response = client.get(f"/api/attachments/{attachment_id}")
    assert response.content == html
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_takeaway_prompt_names_the_files(client, provider):
    conversation_id = new_conversation(client)
    provider.queue.append("Point one. Point two.")
    state = say(client, conversation_id, "start")
    branch_id = open_branch(client, conversation_id, state["main"][-1], "Point one")
    send(client, conversation_id, "see", [{"name": "data.csv", "data": b64(b"a,b\n1,2")}], branch_id)
    provider.queue.append('[{"title": "t", "text": "x"}]')
    client.post(f"/api/branches/{branch_id}/takeaway", json={})
    assert "[document attached: data.csv]" in provider.calls[-1][1][-1].content


def test_migration_keeps_existing_images(tmp_path):
    """Images stored by migration 0003 survive the rebuild of the table in 0004."""
    import sqlite3
    from pathlib import Path

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for number in (1, 2, 3):
        file = next(Path(db.MIGRATIONS_DIR).glob(f"{number:04d}_*.sql"))
        conn.executescript(file.read_text(encoding="utf-8"))
    conn.execute("PRAGMA user_version = 3")
    conn.execute("INSERT INTO conversation VALUES (1, 't', '2026-01-01T00:00:00')")
    conn.execute("INSERT INTO message VALUES (1, 1, NULL, NULL, 'user', 'q', '2026-01-01T00:00:00')")
    conn.execute(
        "INSERT INTO attachment VALUES (1, 1, 0, 'image', 'image/png', 'a.png', 3, x'010203', '2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    migrated = db.connect(path)
    assert migrated.execute("PRAGMA user_version").fetchone()[0] >= 4
    found, data = db.attachment_data(migrated, 1)
    assert (found.kind, found.chars, data) == ("image", None, b"\x01\x02\x03")
