"""Use cases of the HTTP API (docs/API.md).

This is glue. Every rule about the conversation tree is decided by ``core.tree``
and every model input is built by ``core.context``; this module loads the state
from SQLite, calls them, calls the provider and stores the result.

``core`` is always reached through its modules (``tree.merge_branch`` and so on),
never by importing the functions, so that a function that is still a stub fails
at call time with ``NotImplementedError`` (reported as HTTP 501 by ``api.app``).
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone

from api import db, takeaway
from api.config import Config
from api.provider import (
    ChatMessage,
    Completion,
    FakeProvider,
    ModelInfo,
    OpenRouterProvider,
    Provider,
    ProviderError,
    fetch_free_models,
)
from api.settings import SettingsStore, effective_api_key, key_hint
from core import context, tree
from core.models import Branch, BranchStatus, CallPurpose, Message, Role, TakeawayPoint

DEFAULT_TITLE = "New chat"
TITLE_LENGTH = 60
MODELS_CACHE_S = 600


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


def _title_from(content: str) -> str:
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if len(first_line) <= TITLE_LENGTH:
        return first_line or DEFAULT_TITLE
    return first_line[: TITLE_LENGTH - 1].rstrip() + "…"


# --- JSON shapes of docs/API.md -------------------------------------------------------


def _message_json(message: Message) -> dict:
    return {
        "id": message.id,
        "branch_id": message.branch_id,
        "parent_id": message.parent_id,
        "role": message.role.value,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
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
    }


def _branch_json(branch: Branch, messages: Sequence[Message], points: Sequence[TakeawayPoint]) -> dict:
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
        "messages": [_message_json(m) for m in tree.thread(messages, branch.id)],
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
    ) -> None:
        self.config = config
        self.settings = settings or SettingsStore(config.settings_path)
        self._provider_factory = provider_factory or self._default_provider
        self._models_fetcher = models_fetcher
        self._now = clock or (lambda: datetime.now(timezone.utc))
        self._busy: set[tuple] = set()
        self._busy_lock = threading.Lock()
        self._models: tuple[float, list[ModelInfo]] | None = None
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
            "main": [_message_json(m) for m in tree.thread(messages)],
            "branches": [_branch_json(b, messages, points) for b in branches],
            "pending_branch_ids": pending,
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
    ) -> Completion:
        """Call the model and log the call (DESIGN.md §4: every LLM call is logged)."""
        try:
            completion = provider.complete(model, prompt, tag=purpose.value)
        except ProviderError as error:
            code = _PROVIDER_CODES.get(error.kind, "provider_error")
            raise ApiError(502, code, error.message) from error
        with db.transaction(conn):
            db.insert_log(
                conn,
                conversation_id=conversation_id,
                branch_id=branch_id,
                purpose=purpose,
                model=completion.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                cost_estimate=completion.cost,
                prompt_json=json.dumps(
                    [{"role": m.role, "content": m.content} for m in prompt], ensure_ascii=False
                ),
                response_text=completion.text,
                now=self._now(),
            )
        return completion

    def _build_context(
        self, conn: sqlite3.Connection, conversation_id: int, branch: Branch | None
    ) -> list[ChatMessage]:
        """Ask core for the exact model input of the next call on a thread (DESIGN.md §7)."""
        messages, branches, points = db.load_state(conn, conversation_id)
        if branch is None:
            built = context.build_main_context(messages, branches, points)
        else:
            built = context.build_branch_context(branch, messages, branches, points)
        return [ChatMessage(m.role, m.content) for m in built.messages]

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
        completion = self._call(
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
            db.insert_message(
                conn,
                conversation_id=conversation_id,
                branch_id=branch_id,
                parent_id=thread[-1].id,
                role=Role.ASSISTANT,
                content=completion.text,
                now=self._now(),
            )
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

    def send_message(self, conversation_id: int, content: str, branch_id: int | None) -> dict:
        content = content.strip()
        if not content:
            raise invalid("The message is empty.")
        with self._connect() as conn:
            self._chat_branch(conn, conversation_id, branch_id)
            provider, model = self._model_access(conn, for_takeaway=False)
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
                    db.insert_message(
                        conn,
                        conversation_id=conversation_id,
                        branch_id=branch_id,
                        parent_id=thread[-1].id if thread else None,
                        role=Role.USER,
                        content=content,
                        now=self._now(),
                    )
                    conversation = db.get_conversation(conn, conversation_id)
                    if branch_id is None and not thread and conversation.title == DEFAULT_TITLE:
                        db.rename_conversation(conn, conversation_id, _title_from(content))
                    prompt = self._build_context(conn, conversation_id, branch)
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
            busy = "A reply is already being generated on this thread."
            with self._exclusive(("chat", conversation_id, branch_id), busy):
                prompt = self._build_context(conn, conversation_id, branch)
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
            if db.branch_points(conn, branch.id) and not regenerate:
                return self._state(conn, conversation_id)  # cached: never regenerated silently

            provider, model = self._model_access(conn, for_takeaway=True)
            busy = "The take-away of this branch is already being generated."
            with self._exclusive(("takeaway", branch.id), busy):
                call = dict(conversation_id=conversation_id, branch_id=branch.id, purpose=CallPurpose.TAKEAWAY)
                prompt = takeaway.build_prompt(branch.anchor_quote, thread)
                answer = self._call(conn, provider, model, prompt, **call).text
                try:
                    generated = takeaway.parse(answer)
                except takeaway.TakeawayParseError:
                    # One more attempt, showing the model its unreadable answer.
                    answer = self._call(
                        conn, provider, model, takeaway.retry_prompt(prompt, answer), **call
                    ).text
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

    def update_point(self, point_id: int, *, included: bool | None, text_final: str | None) -> dict:
        if included is None and text_final is None:
            raise invalid("Nothing to change.")
        if text_final is not None and not text_final.strip():
            raise invalid("The text of a point cannot be blank: untick the point instead.")
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
                db.update_point(conn, point_id, included=included, text_final=text_final)
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

    # --- settings and models ------------------------------------------------------

    def settings_view(self) -> dict:
        settings = self.settings.load()
        api_key, from_env = effective_api_key(settings)
        with self._connect() as conn:
            spent = db.month_spend(conn, self._now())
        return {
            "has_api_key": bool(api_key),
            "api_key_hint": key_hint(api_key),
            "api_key_from_env": from_env,
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
                {"id": m.id, "name": m.name, "context_length": m.context_length}
                for m in self._models[1]
            ]
        }
