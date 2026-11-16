"""Fixtures for the backend tests.

The API is tested on the real ``core``: these are integration tests of
``api`` + ``core`` against a scripted provider (no network).
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

TEST_KEY = "sk-or-v1-test-key-0001"
TEST_MODEL = "vendor/chat:free"


@pytest.fixture(autouse=True)
def no_key_in_environment(monkeypatch):
    """The developer's own OPENROUTER_API_KEY must not leak into the tests."""
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
