"""Use cases of the HTTP API (docs/API.md).

This is glue. Every rule about the conversation tree is decided by ``core.tree``
and every model input is built by ``core.context``; this module loads the state
from SQLite, calls them, calls the provider and stores the result.

``core`` is always reached through its modules (``tree.merge_branch`` and so on),
never by importing the functions, so that a function that is still a stub fails
at call time with ``NotImplementedError`` (reported as HTTP 501 by ``api.app``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from api import db, documents, takeaway
from api.config import Config
from api.provider import (
    ChatMessage,
    ImagePart,
    Completion,
    OAUTH_URL,
    FakeProvider,
    KeyInfo,
    ModelInfo,
    OpenRouterProvider,
    Provider,
    ProviderError,
    check_key,
    exchange_oauth_code,
    fetch_free_models,
    message_payload,
)
from api.settings import SettingsStore, effective_api_key, key_hint
from core import context, tree
from core.models import Branch, BranchStatus, CallPurpose, Message, PointOrigin, Role, TakeawayPoint

DEFAULT_TITLE = "New chat"
TITLE_LENGTH = 60
MODELS_CACHE_S = 600
OAUTH_TTL_S = 600  # OpenRouter's codes expire after 10 minutes

# Files on a user message (docs/API.md, "Chat"): images, sent as images, and documents,
# sent as their extracted text (api/documents.py). Images are recognised by their first
# bytes, in the types every vision model on OpenRouter accepts.
MAX_FILES = 6
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),  # plus "WEBP" at offset 8, checked below
}
IMAGE_OMITTED = "[image not sent: the selected model does not accept images]"


class ApiError(Exception):
    """An error with the status and code of docs/API.md."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


def conflict(message: str) -> ApiError:
    return ApiError(409, "conflict", message)


def invalid(message: str) -> ApiError:
    return ApiError(422, "validation", message)


_PROVIDER_CODES = {"auth": "provider_auth", "rate_limit": "provider_rate_limit"}


@dataclass(frozen=True)
class Upload:
    """A file as it arrives with a new message, already decoded from base64."""

    name: str
    mime: str  # as the client says; informative only
    data: bytes


ImageUpload = Upload  # the name used before documents existed


@dataclass(frozen=True)
class Prepared:
    """A checked file, ready to store: ``kind`` image or document, ``text`` for documents."""

    kind: str
    name: str
    mime: str
    data: bytes
    text: str | None = None


def _sniff_image(data: bytes) -> str | None:
    """The MIME type of an image from its first bytes, or None if it is not a supported one."""
    for mime, signatures in IMAGE_SIGNATURES.items():
        if any(data.startswith(sig) for sig in signatures):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    return None


def _prepare_files(files: Sequence[Upload]) -> list[Prepared]:
    """Check the files of a new message and read the text of its documents.

    The kind comes from the bytes: an image signature makes an image, anything else
    must be a document ``api.documents`` can read. Nothing is stored if one file is
    refused, so the user can fix it and send again.
    """
    if len(files) > MAX_FILES:
        raise invalid(f"At most {MAX_FILES} files per message.")
    prepared = []
    for upload in files:
        name = (upload.name or "file").strip()[:200] or "file"
        if not upload.data:
            raise invalid(f"{name!r} is empty.")
        mime = _sniff_image(upload.data)
        if mime is not None:
            if len(upload.data) > MAX_IMAGE_BYTES:
                raise invalid(f"The image {name!r} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
            prepared.append(Prepared("image", name, mime, upload.data))
            continue
        kind = documents.document_kind(name, upload.data)
        if kind is None:
            raise invalid(
                f"{name!r} is not a supported file: images (PNG, JPEG, GIF, WebP), PDF, "
                "Word (.docx), or plain text and code."
            )
        try:
            text = documents.extract_text(kind, name, upload.data)
        except documents.DocumentError as error:
            raise invalid(str(error)) from error
        prepared.append(Prepared("document", name, documents.DOCUMENT_MIME[kind], upload.data, text))
    if sum(1 for p in prepared if p.kind == "image") > MAX_IMAGES:
        raise invalid(f"At most {MAX_IMAGES} images per message.")
    return prepared


def _title_from(content: str) -> str:
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if len(first_line) <= TITLE_LENGTH:
        return first_line or DEFAULT_TITLE
    return first_line[: TITLE_LENGTH - 1].rstrip() + "…"


# --- JSON shapes of docs/API.md -------------------------------------------------------


def _message_json(message: Message, attachments: dict[int, list[db.Attachment]]) -> dict:
    return {
        "id": message.id,
        "branch_id": message.branch_id,
        "parent_id": message.parent_id,
        "role": message.role.value,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "attachments": [
            {"id": a.id, "kind": a.kind, "mime": a.mime, "name": a.name, "size": a.size, "chars": a.chars}
            for a in attachments.get(message.id, [])
        ],
    }


def _point_json(point: TakeawayPoint) -> dict:
    return {
        "id": point.id,
        "branch_id": point.branch_id,
        "position": point.position,
        "title": point.title,
        "text_generated": point.text_generated,
        "text_final": point.text_final,
        "included": point.included,
        "origin": point.origin.value,
    }


def _branch_json(
    branch: Branch,
    messages: Sequence[Message],
    points: Sequence[TakeawayPoint],
    attachments: dict[int, list[db.Attachment]],
) -> dict:
    own_points = sorted((p for p in points if p.branch_id == branch.id), key=lambda p: p.position)
    return {
        "id": branch.id,
        "anchor_message_id": branch.anchor_message_id,
        "anchor_start": branch.anchor_start,
        "anchor_end": branch.anchor_end,
        "anchor_quote": branch.anchor_quote,
        "status": branch.status.value,
        "merge_message_id": branch.merge_message_id,
        "base_message_id": branch.base_message_id,
        "created_at": branch.created_at.isoformat(),
        "messages": [_message_json(m, attachments) for m in tree.thread(messages, branch.id)],
        "points": [_point_json(p) for p in own_points],
    }


class Service:
    def __init__(
        self,
        config: Config,
        settings: SettingsStore | None = None,
        *,
        provider_factory: Callable[[str], Provider] | None = None,
        models_fetcher: Callable[[], list[ModelInfo]] = fetch_free_models,
        clock: Callable[[], datetime] | None = None,
        key_checker: Callable[[str], KeyInfo] = check_key,
        oauth_exchanger: Callable[[str, str], str] = exchange_oauth_code,
    ) -> None:
        self.config = config
        self.settings = settings or SettingsStore(config.settings_path)
        self._provider_factory = provider_factory or self._default_provider
        self._models_fetcher = models_fetcher
        self._now = clock or (lambda: datetime.now(timezone.utc))
        self._busy: set[tuple] = set()
        self._busy_lock = threading.Lock()
        self._models: tuple[float, list[ModelInfo]] | None = None
        self._key_checker = key_checker
        self._oauth_exchanger = oauth_exchanger
        self._key_info: tuple[str, KeyInfo] | None = None  # the last check, for the key it checked
        self._oauth: dict[str, tuple[str, float]] = {}  # state -> (code_verifier, started at)
        db.connect(config.db_path).close()  # create and migrate the database up front

    def _default_provider(self, api_key: str) -> Provider:
        return FakeProvider() if self.config.fake_llm else OpenRouterProvider(api_key)

    # --- helpers ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = db.connect(self.config.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _exclusive(self, key: tuple, message: str) -> Iterator[None]:
        """Refuse to run two model calls for the same thread (or branch take-away) at once."""
        with self._busy_lock:
            if key in self._busy:
                raise conflict(message)
            self._busy.add(key)
        try:
            yield
        finally:
            with self._busy_lock:
                self._busy.discard(key)

    def _is_busy(self, key: tuple) -> bool:
        with self._busy_lock:
            return key in self._busy

    def _state(self, conn: sqlite3.Connection, conversation_id: int) -> dict:
        conversation = db.get_conversation(conn, conversation_id)
        if conversation is None:
            raise not_found("Conversation")
        messages, branches, points = db.load_state(conn, conversation_id)
        attachments = db.load_attachments(conn, conversation_id)
        try:
            pending: list[int] | None = [b.id for b in tree.pending_branches(branches)]
        except NotImplementedError:
            pending = None  # the UI falls back to counting open branches
        return {
            "conversation": {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
            },
            "main": [_message_json(m, attachments) for m in tree.thread(messages)],
            "branches": [_branch_json(b, messages, points, attachments) for b in branches],
            "pending_branch_ids": pending,
            "usage": db.usage(conn, conversation_id),
        }

    def _check(self, conn: sqlite3.Connection, conversation_id: int) -> None:
        """Validate the whole conversation with core before committing a change."""
        try:
            tree.check_invariants(*db.load_state(conn, conversation_id))
        except NotImplementedError:
            pass  # still a stub: the single-operation checks of core.tree still apply

    def _require_branch(self, conn: sqlite3.Connection, branch_id: int) -> Branch:
        branch = db.get_branch(conn, branch_id)
        if branch is None:
            raise not_found("Branch")
        return branch

    def _chat_branch(
        self, conn: sqlite3.Connection, conversation_id: int, branch_id: int | None
    ) -> Branch | None:
        """The branch a chat request targets (None = main), checked for existence and state."""
        if db.get_conversation(conn, conversation_id) is None:
            raise not_found("Conversation")
        if branch_id is None:
            return None
        branch = db.get_branch(conn, branch_id)
        if branch is None or branch.conversation_id != conversation_id:
            raise not_found("Branch")
        if branch.status != BranchStatus.OPEN:
            raise conflict(f"This branch is {branch.status.value}: it cannot be continued.")
        return branch

    def _model_access(self, conn: sqlite3.Connection, *, for_takeaway: bool) -> tuple[Provider, str]:
        """The provider and model for the next call, or the reason no call can be made."""
        settings = self.settings.load()
        model = (settings.takeaway_model if for_takeaway else None) or settings.chat_model
        if self.config.fake_llm:
            return self._provider_factory(""), model or FakeProvider.MODEL
        api_key, _ = effective_api_key(settings)
        if not api_key:
            raise ApiError(400, "no_api_key", "No OpenRouter API key is configured. Add it in Settings.")
        if not model:
            raise ApiError(400, "no_model", "No model is selected. Choose one in Settings.")
        cap, spent = settings.spend_cap_usd, db.month_spend(conn, self._now())
        if (cap > 0 and spent >= cap) or (cap == 0 and spent > 0):
            raise ApiError(
                402,
                "spend_cap_reached",
                f"Monthly spend cap reached (${spent:.4f} spent, cap ${cap:.2f}). "
                "No call was made. Raise the cap in Settings to continue.",
            )
        return self._provider_factory(api_key), model

    def _call(
        self,
        conn: sqlite3.Connection,
        provider: Provider,
        model: str,
        prompt: Sequence[ChatMessage],
        *,
        conversation_id: int,
        branch_id: int | None,
        purpose: CallPurpose,
    ) -> tuple[Completion, int]:
        """Call the model and log the call (DESIGN.md §4: every LLM call is logged).

        Returns the completion and the id of its row in ``llm_call_log``."""
        try:
            completion = provider.complete(model, prompt, tag=purpose.value)
        except ProviderError as error:
            code = _PROVIDER_CODES.get(error.kind, "provider_error")
            raise ApiError(502, code, error.message) from error
        with db.transaction(conn):
            log_id = db.insert_log(
                conn,
                conversation_id=conversation_id,
                branch_id=branch_id,
                purpose=purpose,
                model=completion.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                cost_estimate=completion.cost,
                # Images appear as "attachment:<id>": the bytes are in the attachment table.
                prompt_json=json.dumps(
                    [message_payload(m, inline_images=False) for m in prompt], ensure_ascii=False
                ),
                response_text=completion.text,
                now=self._now(),
            )
        return completion, log_id

    def _build_context(
        self,
        conn: sqlite3.Connection,
        conversation_id: int,
        branch: Branch | None,
        *,
        images: bool = True,
    ) -> list[ChatMessage]:
        """Ask core for the exact model input of the next call on a thread (DESIGN.md §7).

        core builds the text. Each message then gets the files of the stored
        message it renders (``ContextMessage.source_id``): the text of its
        documents, each in ``<document>`` delimiters after what the user typed
        (DESIGN.md §14.13), and its images. With ``images=False`` (a model known
        not to accept them) every image is replaced by a short note, so the call
        does not fail and the log says what was left out.
        """
        messages, branches, points = db.load_state(conn, conversation_id)
        if branch is None:
            built = context.build_main_context(messages, branches, points)
        else:
            built = context.build_branch_context(branch, messages, branches, points)
        attachments = db.load_attachments(conn, conversation_id)
        prompt = []
        for m in built.messages:
            own = attachments.get(m.source_id, []) if m.source_id is not None else []
            texts = [m.content] if m.content else []
            parts = []
            for a in own:
                if a.kind == "document":
                    texts.append(documents.render_document(a.name, db.attachment_text(conn, a.id) or ""))
                elif images:
                    found = db.attachment_data(conn, a.id)
                    if found is not None:
                        parts.append(ImagePart(mime=a.mime, data=found[1], ref=f"attachment:{a.id}"))
                else:
                    texts.append(IMAGE_OMITTED)
            prompt.append(ChatMessage(m.role, "\n\n".join(texts), tuple(parts)))
        return prompt

    def _accepts_images(self, model: str) -> bool | None:
        """Whether ``model`` takes images, from OpenRouter's model list. None = unknown."""
        if self.config.fake_llm:
            return True
        try:
            listed = self.models()["models"]
        except ApiError:
            return None  # the list could not be fetched: let the provider decide
        for m in listed:
            if m["id"] == model:
                return bool(m["images"])
        return None  # not a listed free model (typed by hand): unknown

    def _reply(
        self,
        conn: sqlite3.Connection,
        conversation_id: int,
        branch_id: int | None,
        provider: Provider,
        model: str,
        prompt: Sequence[ChatMessage],
    ) -> dict:
        """Call the model for a thread that ends with a user message and store the answer."""
        completion, call_id = self._call(
            conn,
            provider,
            model,
            prompt,
            conversation_id=conversation_id,
            branch_id=branch_id,
            purpose=CallPurpose.CHAT,
        )
        with db.transaction(conn):
            thread = tree.thread(db.load_messages(conn, conversation_id), branch_id)
            if not thread or thread[-1].role != Role.USER:
                raise conflict("The thread changed while the model was answering; the answer was dropped.")
            answer = db.insert_message(
                conn,
                conversation_id=conversation_id,
                branch_id=branch_id,
                parent_id=thread[-1].id,
                role=Role.ASSISTANT,
                content=completion.text,
                now=self._now(),
            )
            db.link_call(conn, call_id, answer.id)
            self._check(conn, conversation_id)
        return self._state(conn, conversation_id)

    # --- conversations ------------------------------------------------------------

    def list_conversations(self) -> dict:
        with self._connect() as conn:
            return {
                "conversations": [
                    {
                        "id": conversation.id,
                        "title": conversation.title,
                        "created_at": conversation.created_at.isoformat(),
                        "open_branches": open_branches,
                    }
                    for conversation, open_branches in db.list_conversations(conn)
                ]
            }

    def create_conversation(self, title: str | None) -> dict:
        title = (title or "").strip() or DEFAULT_TITLE
        with self._connect() as conn:
            with db.transaction(conn):
                conversation = db.create_conversation(conn, title, self._now())
            return self._state(conn, conversation.id)

    def get_conversation(self, conversation_id: int) -> dict:
        with self._connect() as conn:
            return self._state(conn, conversation_id)

    def rename_conversation(self, conversation_id: int, title: str) -> dict:
        title = title.strip()
        if not title:
            raise invalid("The title cannot be empty.")
        with self._connect() as conn:
            if db.get_conversation(conn, conversation_id) is None:
                raise not_found("Conversation")
            with db.transaction(conn):
                db.rename_conversation(conn, conversation_id, title)
            return self._state(conn, conversation_id)

    # --- chat ---------------------------------------------------------------------

    def send_message(
        self,
        conversation_id: int,
        content: str,
        branch_id: int | None,
        files: Sequence[Upload] = (),
    ) -> dict:
        content = content.strip()
        files = _prepare_files(files)
        images = [f for f in files if f.kind == "image"]
        if not content and not files:
            raise invalid("The message is empty.")
        with self._connect() as conn:
            self._chat_branch(conn, conversation_id, branch_id)
            provider, model = self._model_access(conn, for_takeaway=False)
            vision = self._accepts_images(model)
            if images and vision is False:
                raise invalid(
                    f"The model {model} does not accept images. Choose a model marked "
                    "'images' in Settings, or send the message without them."
                )
            busy = "A reply is already being generated on this thread."
            with self._exclusive(("chat", conversation_id, branch_id), busy):
                # Nothing is stored unless the context can be built: a core stub
                # or a broken invariant rolls the user message back.
                with db.transaction(conn):
                    branch = self._chat_branch(conn, conversation_id, branch_id)
                    thread = tree.thread(db.load_messages(conn, conversation_id), branch_id)
                    if thread and thread[-1].role == Role.USER:
                        raise conflict(
                            "This thread is waiting for a reply to its last message: "
                            "retry it or delete it first."
                        )
                    stored = db.insert_message(
                        conn,
                        conversation_id=conversation_id,
                        branch_id=branch_id,
                        parent_id=thread[-1].id if thread else None,
                        role=Role.USER,
                        content=content,
                        now=self._now(),
                    )
                    for position, file in enumerate(files):
                        db.insert_attachment(
                            conn,
                            message_id=stored.id,
                            position=position,
                            kind=file.kind,
                            mime=file.mime,
                            name=file.name,
                            data=file.data,
                            text=file.text,
                            now=self._now(),
                        )
                    conversation = db.get_conversation(conn, conversation_id)
                    if branch_id is None and not thread and conversation.title == DEFAULT_TITLE:
                        title = _title_from(content) if content else _title_from(files[0].name)
                        db.rename_conversation(conn, conversation_id, title)
                    prompt = self._build_context(conn, conversation_id, branch, images=vision is not False)
                    self._check(conn, conversation_id)
                # From here on the user message is stored: a provider failure
                # leaves it there, to be retried with generate() or deleted.
                return self._reply(conn, conversation_id, branch_id, provider, model, prompt)

    def generate(self, conversation_id: int, branch_id: int | None) -> dict:
        """Retry the model call for a thread that ends with a user message."""
        with self._connect() as conn:
            branch = self._chat_branch(conn, conversation_id, branch_id)
            thread = tree.thread(db.load_messages(conn, conversation_id), branch_id)
            if not thread or thread[-1].role != Role.USER:
                raise conflict("This thread is not waiting for a reply.")
            provider, model = self._model_access(conn, for_takeaway=False)
            images = self._accepts_images(model) is not False
            busy = "A reply is already being generated on this thread."
            with self._exclusive(("chat", conversation_id, branch_id), busy):
                prompt = self._build_context(conn, conversation_id, branch, images=images)
                return self._reply(conn, conversation_id, branch_id, provider, model, prompt)

    def delete_message(self, message_id: int) -> dict:
        """Remove a user message left without a reply (the last message of its thread)."""
        with self._connect() as conn:
            message = db.get_message(conn, message_id)
            if message is None:
                raise not_found("Message")
            if self._is_busy(("chat", message.conversation_id, message.branch_id)):
                raise conflict("A reply to this message is being generated.")
            with db.transaction(conn):
                thread = tree.thread(db.load_messages(conn, message.conversation_id), message.branch_id)
                if message.role != Role.USER or not thread or thread[-1].id != message.id:
                    raise conflict("Only a user message without a reply can be deleted.")
                if message.branch_id is not None:
                    branch = self._require_branch(conn, message.branch_id)
                    if branch.status != BranchStatus.OPEN:
                        raise conflict(f"This branch is {branch.status.value}: it cannot be changed.")
                db.delete_message(conn, message.id)
                self._check(conn, message.conversation_id)
            return self._state(conn, message.conversation_id)

    # --- branches -----------------------------------------------------------------

    def open_branch(
        self, conversation_id: int, anchor_message_id: int, start: int, end: int, quote: str
    ) -> dict:
        with self._connect() as conn:
            if db.get_conversation(conn, conversation_id) is None:
                raise not_found("Conversation")
            with db.transaction(conn):
                anchor = db.get_message(conn, anchor_message_id)
                if anchor is None or anchor.conversation_id != conversation_id:
                    raise not_found("Anchor message")
                in_range = 0 <= start < end <= len(anchor.content)
                if in_range and anchor.content[start:end] != quote:
                    raise invalid(
                        "The selected text does not match the message at these offsets "
                        "(offsets must be Python string offsets, in code points)."
                    )
                # The branch starts from main as it is now: take-aways merged so far are
                # visible in it, even when the merge came after the anchor (DESIGN.md §14.11).
                main = tree.thread(db.load_messages(conn, conversation_id))
                # Out-of-range offsets and every rule about the anchor are core's to refuse.
                branch = tree.open_branch(
                    anchor,
                    start,
                    end,
                    new_id=db.next_branch_id(conn),
                    created_at=self._now(),
                    base_message_id=main[-1].id if main else None,
                )
                db.insert_branch(conn, branch)
                self._check(conn, conversation_id)
            return {"branch_id": branch.id, "state": self._state(conn, conversation_id)}

    def discard_branch(self, branch_id: int) -> dict:
        with self._connect() as conn:
            with db.transaction(conn):
                branch = self._require_branch(conn, branch_id)
                db.update_branch_status(conn, tree.discard_branch(branch))
                self._check(conn, branch.conversation_id)
            return self._state(conn, branch.conversation_id)

    def generate_takeaway(self, branch_id: int, regenerate: bool) -> dict:
        """Generate (once) and cache the take-away points of a branch (DESIGN.md §8)."""
        with self._connect() as conn:
            branch = self._require_branch(conn, branch_id)
            conversation_id = branch.conversation_id
            if branch.status != BranchStatus.OPEN:
                raise conflict(f"This branch is {branch.status.value}: its take-away cannot change.")
            thread = tree.thread(db.load_messages(conn, conversation_id), branch.id)
            if not thread:
                raise conflict("An empty branch has nothing to bring back: it can only be discarded.")
            generated_before = any(p.origin == PointOrigin.MODEL for p in db.branch_points(conn, branch.id))
            if generated_before and not regenerate:
                return self._state(conn, conversation_id)  # cached: never regenerated silently

            provider, model = self._model_access(conn, for_takeaway=True)
            busy = "The take-away of this branch is already being generated."
            with self._exclusive(("takeaway", branch.id), busy):
                call = dict(conversation_id=conversation_id, branch_id=branch.id, purpose=CallPurpose.TAKEAWAY)
                files = {
                    message_id: [(a.kind, a.name) for a in found]
                    for message_id, found in db.load_attachments(conn, conversation_id).items()
                }
                prompt = takeaway.build_prompt(branch.anchor_quote, thread, files)
                answer = self._call(conn, provider, model, prompt, **call)[0].text
                try:
                    generated = takeaway.parse(answer)
                except takeaway.TakeawayParseError:
                    # One more attempt, showing the model its unreadable answer.
                    answer = self._call(
                        conn, provider, model, takeaway.retry_prompt(prompt, answer), **call
                    )[0].text
                    try:
                        generated = takeaway.parse(answer)
                    except takeaway.TakeawayParseError as error:
                        raise ApiError(
                            502,
                            "takeaway_parse",
                            f"The model did not return a usable take-away ({error}). Try again.",
                        ) from error
                with db.transaction(conn):
                    if self._require_branch(conn, branch.id).status != BranchStatus.OPEN:
                        raise conflict("The branch was closed while its take-away was being generated.")
                    db.replace_points(conn, branch.id, [(p.title, p.text) for p in generated])
                    self._check(conn, conversation_id)
            return self._state(conn, conversation_id)

    def _open_point_branch(self, conn: sqlite3.Connection, branch_id: int) -> Branch:
        branch = self._require_branch(conn, branch_id)
        if branch.status != BranchStatus.OPEN:
            raise conflict(
                f"This branch is {branch.status.value}: its points are part of the "
                "conversation history and cannot change."
            )
        return branch

    def add_point(self, branch_id: int, text: str, title: str | None) -> dict:
        """A point the user writes by hand: it enters the context like a generated one (§14.14)."""
        text = text.strip()
        if not text:
            raise invalid("The text of a point cannot be blank.")
        title = takeaway.title_from(title or "") or takeaway.title_from(text)
        with self._connect() as conn:
            with db.transaction(conn):
                branch = self._open_point_branch(conn, branch_id)
                if not tree.thread(db.load_messages(conn, branch.conversation_id), branch.id):
                    raise conflict("An empty branch has nothing to bring back: it can only be discarded.")
                db.add_user_point(conn, branch.id, title, text)
                self._check(conn, branch.conversation_id)
            return self._state(conn, branch.conversation_id)

    def delete_point(self, point_id: int) -> dict:
        """Remove a point the user added. A generated point is unticked instead, never deleted."""
        with self._connect() as conn:
            with db.transaction(conn):
                point = db.get_point(conn, point_id)
                if point is None:
                    raise not_found("Point")
                branch = self._open_point_branch(conn, point.branch_id)
                if point.origin != PointOrigin.USER:
                    raise conflict("A generated point cannot be deleted: untick it instead.")
                db.delete_point(conn, point_id)
                self._check(conn, branch.conversation_id)
            return self._state(conn, branch.conversation_id)

    def update_point(
        self,
        point_id: int,
        *,
        included: bool | None,
        text_final: str | None,
        title: str | None = None,
    ) -> dict:
        if included is None and text_final is None and title is None:
            raise invalid("Nothing to change.")
        if text_final is not None and not text_final.strip():
            raise invalid("The text of a point cannot be blank: untick the point instead.")
        if title is not None:
            title = takeaway.title_from(title)
            if not title:
                raise invalid("The title of a point cannot be blank.")
        with self._connect() as conn:
            with db.transaction(conn):
                point = db.get_point(conn, point_id)
                if point is None:
                    raise not_found("Point")
                branch = self._require_branch(conn, point.branch_id)
                if branch.status != BranchStatus.OPEN:
                    raise conflict(
                        f"This branch is {branch.status.value}: its points are part of the "
                        "conversation history and cannot change."
                    )
                db.update_point(conn, point_id, included=included, text_final=text_final, title=title)
                self._check(conn, branch.conversation_id)
            return self._state(conn, branch.conversation_id)

    def merge(self, conversation_id: int, branch_ids: Sequence[int]) -> dict:
        """Merge branches at the current end of main (DESIGN.md §14.6)."""
        if not branch_ids:
            raise invalid("No branch to merge.")
        if len(set(branch_ids)) != len(branch_ids):
            raise invalid("The same branch is listed twice.")
        with self._connect() as conn:
            if db.get_conversation(conn, conversation_id) is None:
                raise not_found("Conversation")
            if self._is_busy(("chat", conversation_id, None)):
                raise conflict("A reply is being generated on main: merge when it has arrived.")
            with db.transaction(conn):
                branches = []
                for branch_id in branch_ids:
                    branch = db.get_branch(conn, branch_id)
                    if branch is None or branch.conversation_id != conversation_id:
                        raise not_found("Branch")
                    branches.append(branch)

                messages = db.load_messages(conn, conversation_id)
                for branch in branches:
                    # A closed or empty branch is core's to refuse (below); here only the
                    # API-level rule: the user must have seen a take-away before merging.
                    ready = branch.status != BranchStatus.OPEN or not tree.thread(messages, branch.id)
                    if not ready and not db.branch_points(conn, branch.id):
                        raise conflict("Generate the take-away of a branch before merging it.")

                main = tree.thread(messages)
                if main and main[-1].role == Role.USER:
                    raise conflict("Main is waiting for a reply: retry or delete its last message first.")
                # Branches merged together share the merge node at the end of main, unless
                # a branch was opened from that node since: core decides (DESIGN.md §14.11).
                node = tree.reusable_merge_node(messages, db.load_branches(conn, conversation_id))
                if node is None:
                    node = db.insert_message(
                        conn,
                        conversation_id=conversation_id,
                        branch_id=None,
                        parent_id=main[-1].id if main else None,
                        role=Role.MERGE,
                        content="",
                        now=self._now(),
                    )
                messages = db.load_messages(conn, conversation_id)
                for branch in branches:
                    # core decides whether this merge is legal (open, non-empty, node at the end).
                    db.update_branch_status(conn, tree.merge_branch(branch, node, messages))
                self._check(conn, conversation_id)
            return self._state(conn, conversation_id)

    def attachment(self, attachment_id: int) -> tuple[db.Attachment, bytes]:
        """A stored file and its bytes."""
        with self._connect() as conn:
            found = db.attachment_data(conn, attachment_id)
        if found is None:
            raise not_found("Attachment")
        return found

    # --- settings and models ------------------------------------------------------

    def settings_view(self) -> dict:
        settings = self.settings.load()
        api_key, from_env = effective_api_key(settings)
        with self._connect() as conn:
            spent = db.month_spend(conn, self._now())
        info = self._key_info[1] if self._key_info and self._key_info[0] == api_key else None
        return {
            "has_api_key": bool(api_key),
            "api_key_hint": key_hint(api_key),
            "api_key_from_env": from_env,
            "key_info": None
            if info is None
            else {
                "label": info.label,
                "is_free_tier": info.is_free_tier,
                "free_daily_limit": info.free_daily_limit,
                "free_daily_remaining": info.free_daily_remaining,
            },
            "spend_cap_usd": settings.spend_cap_usd,
            "chat_model": settings.chat_model,
            "takeaway_model": settings.takeaway_model,
            "month_spend_usd": spent,
            "fake_llm": self.config.fake_llm,
        }

    def update_settings(self, changes: dict) -> dict:
        """``changes`` holds only the fields the client sent."""
        clean: dict[str, object] = {}
        if "api_key" in changes:
            api_key = (changes["api_key"] or "").strip()
            if not api_key:
                raise invalid("The API key is empty. Use 'Remove' to delete the saved key.")
            self._check_key(api_key)
            clean["api_key"] = api_key
        if "spend_cap_usd" in changes:
            cap = changes["spend_cap_usd"]
            if cap is None or not math.isfinite(cap) or cap < 0:
                raise invalid("The spend cap must be a number of dollars, 0 or more.")
            clean["spend_cap_usd"] = float(cap)
        for field in ("chat_model", "takeaway_model"):
            if field in changes:
                clean[field] = (changes[field] or "").strip() or None
        if clean:
            self.settings.update(**clean)
        return self.settings_view()

    def _check_key(self, api_key: str) -> None:
        """Refuse a key OpenRouter rejects; remember what it says about a good one.

        If OpenRouter cannot be reached the key is saved anyway: working offline
        with the fake model, or a network hiccup, must not block the setup.
        """
        if self.config.fake_llm:
            return
        try:
            self._key_info = (api_key, self._key_checker(api_key))
        except ProviderError as error:
            if error.kind == "auth":
                raise invalid(
                    "OpenRouter rejected this key. Copy it again from openrouter.ai/keys "
                    "(it starts with sk-or-)."
                ) from error

    # --- OpenRouter OAuth (PKCE): get a key by logging in, without copying it ------

    def oauth_start(self, callback_url: str) -> dict:
        """The URL that sends the user to OpenRouter to approve a key for this app."""
        now = time.monotonic()
        self._oauth = {s: v for s, v in self._oauth.items() if now - v[1] < OAUTH_TTL_S}
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(16)
        self._oauth[state] = (verifier, now)
        query = httpx.QueryParams(
            {
                "callback_url": f"{callback_url}?state={state}",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return {"url": f"{OAUTH_URL}?{query}"}

    def oauth_finish(self, code: str, state: str) -> None:
        """Exchange the code OpenRouter sent back for a key, check it and save it."""
        pending = self._oauth.pop(state, None)
        if pending is None or time.monotonic() - pending[1] > OAUTH_TTL_S:
            raise invalid("This OpenRouter login is unknown or expired. Start it again from Settings.")
        try:
            api_key = self._oauth_exchanger(code, pending[0])
        except ProviderError as error:
            raise ApiError(502, "provider_auth", error.message) from error
        self._check_key(api_key)
        self.settings.update(api_key=api_key)

    def delete_api_key(self) -> dict:
        self.settings.update(api_key=None)
        return self.settings_view()

    def models(self) -> dict:
        """Free OpenRouter models, cached for a few minutes."""
        if self._models is None or time.monotonic() - self._models[0] > MODELS_CACHE_S:
            try:
                self._models = (time.monotonic(), self._models_fetcher())
            except ProviderError as error:
                raise ApiError(502, "provider_error", error.message) from error
        return {
            "models": [
                {"id": m.id, "name": m.name, "context_length": m.context_length, "images": m.images}
                for m in self._models[1]
            ]
        }
