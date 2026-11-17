"""Documents attached to a message: what they are, and the text the model receives.

Every document becomes plain text here, on this computer, when it is attached.
The model receives that text, between ``<document>`` delimiters, wherever the
message is part of a context (DESIGN.md §14.13). Extracting locally instead of
letting the provider parse the file keeps the rule "no hidden state": the call
log holds exactly the text the model read, and no parsing engine adds a cost.

Pure functions over bytes, no I/O besides reading them.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_CHARS = 200_000  # about 50k tokens: more would crowd out the conversation
MAX_DOCX_XML_BYTES = 50 * 1024 * 1024  # uncompressed word/document.xml (zip bombs)

# Plain text and source code, recognised by extension and accepted if they decode as text.
TEXT_EXTENSIONS = frozenset(
    """
    txt text md markdown rst org csv tsv json jsonl yaml yml toml ini cfg conf env log xml
    html htm css scss less js mjs cjs jsx ts tsx vue svelte py pyi ipynb java kt kts scala
    groovy c h cc cpp cxx hpp hh cs go rs rb php pl pm swift m mm r jl lua dart ex exs erl
    hs ml fs clj sql sh bash zsh fish ps1 bat cmd dockerfile makefile gradle tex bib srt vtt
    """.split()
)

DOCUMENT_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text": "text/plain",
}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(ValueError):
    """The file cannot be read as a document; the message says why, for the user."""


def extension(name: str) -> str:
    path = PurePath(name.lower())
    if path.suffix:
        return path.suffix[1:]
    return path.name  # "Dockerfile", "Makefile"


def document_kind(name: str, data: bytes) -> str | None:
    """``pdf``, ``docx`` or ``text`` from the bytes (and, for text, the extension); None otherwise."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") and extension(name) == "docx":
        return "docx"
    if extension(name) in TEXT_EXTENSIONS:
        return "text"
    return None


def extract_text(kind: str, name: str, data: bytes) -> str:
    """The text of a document of the given kind.

    Raises:
        DocumentError: unreadable, empty, encrypted, or longer than MAX_DOCUMENT_CHARS.
    """
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentError(f"{name} is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.")
    if kind == "pdf":
        text = _pdf_text(name, data)
    elif kind == "docx":
        text = _docx_text(name, data)
    elif kind == "text":
        text = _plain_text(name, data)
    else:
        raise DocumentError(f"{name}: unsupported kind of document.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        if kind == "pdf":
            raise DocumentError(f"{name} has no text to read (a scanned PDF? Send its pages as images).")
        raise DocumentError(f"{name} is empty.")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise DocumentError(
            f"{name} has {len(text):,} characters of text; the limit is {MAX_DOCUMENT_CHARS:,}. "
            "Send the part that matters."
        )
    return text


def render_document(name: str, text: str) -> str:
    """The block the model receives for one document."""
    safe = name.replace('"', "'").replace("\n", " ")
    return f'<document name="{safe}">\n{text}\n</document>'


def _plain_text(name: str, data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as error:
            raise DocumentError(f"{name} is not valid UTF-16 text.") from error
    if b"\x00" in data:
        raise DocumentError(f"{name} looks like a binary file, not text.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentError(f"{name} is not UTF-8 text.") from error


def _pdf_text(name: str, data: bytes) -> str:
    from pypdf import PdfReader  # imported here: only needed when a PDF arrives
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError(f"{name} is protected by a password.")
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[page {number}]\n{text}")
        return "\n\n".join(pages)
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as error:
        raise DocumentError(f"{name} could not be read as a PDF.") from error


def _docx_text(name: str, data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise DocumentError(f"{name} is too large once unpacked.")
            xml = archive.read(info)
    except DocumentError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise DocumentError(f"{name} could not be read as a Word document.") from error
    if b"<!DOCTYPE" in xml[:2048]:
        raise DocumentError(f"{name} could not be read as a Word document.")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise DocumentError(f"{name} could not be read as a Word document.") from error

    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)
