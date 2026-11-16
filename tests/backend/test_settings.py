"""Tests for ``api.settings``."""

from __future__ import annotations

import json

from api.settings import ENV_KEY, Settings, SettingsStore, effective_api_key, key_hint


def test_missing_file_gives_defaults(tmp_path):
    assert SettingsStore(tmp_path / "s.json").load() == Settings()


def test_update_persists_and_keeps_other_fields(tmp_path):
    store = SettingsStore(tmp_path / "deep" / "s.json")
    store.update(api_key="sk-or-v1-abcdefgh1234", chat_model="a/b:free")
    store.update(spend_cap_usd=2.5)
    assert SettingsStore(store.path).load() == Settings(
        api_key="sk-or-v1-abcdefgh1234", spend_cap_usd=2.5, chat_model="a/b:free"
    )
    assert not store.path.with_suffix(".tmp").exists()


def test_corrupt_or_odd_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")
    assert SettingsStore(path).load() == Settings()
    path.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert SettingsStore(path).load() == Settings()
    path.write_text(json.dumps({"spend_cap_usd": "many"}), encoding="utf-8")
    assert SettingsStore(path).load() == Settings()


def test_unknown_fields_are_ignored_and_negative_cap_is_clamped(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"chat_model": "m", "future": 1, "spend_cap_usd": -3}), encoding="utf-8"
    )
    assert SettingsStore(path).load() == Settings(chat_model="m", spend_cap_usd=0.0)


def test_env_key_wins(monkeypatch):
    monkeypatch.delenv(ENV_KEY, raising=False)
    assert effective_api_key(Settings(api_key="saved")) == ("saved", False)
    assert effective_api_key(Settings()) == (None, False)
    monkeypatch.setenv(ENV_KEY, "  from-env  ")
    assert effective_api_key(Settings(api_key="saved")) == ("from-env", True)


def test_key_hint_never_shows_a_short_key():
    assert key_hint(None) is None
    assert key_hint("sk-or-v1-abcdefgh1234") == "…1234"
    assert key_hint("short") == "…"
