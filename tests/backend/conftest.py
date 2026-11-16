"""Fixtures for the backend tests.

The API is written against ``core``, part of which is still being implemented.
So that these tests check the API and nothing else, the ``core`` functions the
API calls for context building and whole-state checks are replaced by the small
STAND-INS below. They are test doubles, not the real thing: deliberately naive,
with their own obvious format, so nobody mistakes them for ``core.context``.
The real functions are exercised by the tests in ``tests/`` proper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.config import Config
from api.provider import ChatMessage, Completion, ModelInfo, ProviderError
from api.service import Service
from api.settings import ENV_KEY, SettingsStore
from core import context, tree
from core.context import Context, ContextMessage
from core.models import BranchStatus, Role

TEST_KEY = "sk-or-v1-test-key-0001"
TEST_MODEL = "vendor/chat:free"


def _plain(messages):
    return [ContextMessage(m.role.value, m.content) for m in messages if m.role != Role.MERGE]


def standin_main_context(messages, branches, points):
    return Context(_plain(tree.thread(messages)))


def standin_branch_context(branch, messages, branches, points):
    main = tree.thread(messages)
    upto = [m.id for m in main].index(branch.anchor_message_id) + 1
    note = ContextMessage("user", f"<standin-anchor>{branch.anchor_quote}</standin-anchor>")
    return Context([*_plain(main[:upto]), note, *_plain(tree.thread(messages, branch.id))])


def standin_pending(branches):
    return [b for b in branches if b.status == BranchStatus.OPEN]


@pytest.fixture(autouse=True)
def core_standins(monkeypatch):
    monkeypatch.setattr(context, "build_main_context", standin_main_context)
    monkeypatch.setattr(context, "build_branch_context", standin_branch_context)
    monkeypatch.setattr(tree, "pending_branches", standin_pending)
    monkeypatch.setattr(tree, "check_invariants", lambda messages, branches, points: None)
    monkeypatch.delenv(ENV_KEY, raising=False)


class ScriptedProvider:
    """A provider that records every call and answers from a queue.

    Queue items are strings (the answer), ``ProviderError`` instances (raised)
    or ``Completion`` objects. With an empty queue it answers ``reply N``.
    """

    def __init__(self) -> None:
        self.queue: list[object] = []
        self.calls: list[tuple[str, list[ChatMessage], str]] = []
        self.cost = 0.0
        self.keys: list[str] = []

    def complete(self, model, messages, *, tag="chat"):
        self.calls.append((model, list(messages), tag))
        item = self.queue.pop(0) if self.queue else f"reply {len(self.calls)}"
        if isinstance(item, ProviderError):
            raise item
        if isinstance(item, Completion):
            return item
        return Completion(text=item, model=model, input_tokens=10, output_tokens=5, cost=self.cost)


class Clock:
    """A clock that moves one second per reading, so rows have distinct, ordered timestamps."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 9, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def provider() -> ScriptedProvider:
    return ScriptedProvider()


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        home=tmp_path,
        db_path=tmp_path / "graftchat.db",
        fake_llm=False,
        web_dist=tmp_path / "no-dist",
        port=0,
    )


@pytest.fixture
def service(config, provider) -> Service:
    def factory(api_key: str) -> ScriptedProvider:
        provider.keys.append(api_key)
        return provider

    models = [ModelInfo("vendor/chat:free", "Chat", 8000), ModelInfo("vendor/small:free", "Small", None)]
    service = Service(
        config,
        SettingsStore(config.settings_path),
        provider_factory=factory,
        models_fetcher=lambda: models,
        clock=Clock(),
    )
    service.settings.update(api_key=TEST_KEY, chat_model=TEST_MODEL)
    return service


@pytest.fixture
def client(service) -> TestClient:
    return TestClient(create_app(service), raise_server_exceptions=False)
