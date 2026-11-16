"""User settings: the BYOK API key, the spend cap and the chosen models (DESIGN.md §4, §5).

They live in one JSON file on this computer, outside the repository. The key is
never returned by the API (only a hint) and never written to the database or to
``llm_call_log``.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

ENV_KEY = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class Settings:
    api_key: str | None = None
    spend_cap_usd: float = 0.0  # 0 = free models only
    chat_model: str | None = None
    takeaway_model: str | None = None  # None = same as chat_model


class SettingsStore:
    """Reads and writes the settings file. Safe to share between request threads."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> Settings:
        with self._lock:
            return self._read()

    def update(self, **changes: object) -> Settings:
        """Change some fields and save. Returns the new settings."""
        with self._lock:
            settings = replace(self._read(), **changes)
            self._write(settings)
            return settings

    def _read(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, json.JSONDecodeError):
            # An unreadable file must not lock the user out of the app: start from defaults.
            return Settings()
        if not isinstance(raw, dict):
            return Settings()
        known = {name: raw[name] for name in Settings.__dataclass_fields__ if name in raw}
        try:
            settings = Settings(**known)
            return replace(settings, spend_cap_usd=max(0.0, float(settings.spend_cap_usd)))
        except (TypeError, ValueError):
            return Settings()

    def _write(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)  # owner-only where the OS supports it
        except OSError:
            pass
        os.replace(temporary, self.path)


def effective_api_key(settings: Settings) -> tuple[str | None, bool]:
    """The key to use and whether it comes from the environment (which wins)."""
    from_env = os.environ.get(ENV_KEY, "").strip()
    if from_env:
        return from_env, True
    return (settings.api_key or None), False


def key_hint(key: str | None) -> str | None:
    """A recognisable but useless fragment of the key, for the settings screen."""
    if not key:
        return None
    return "…" + key[-4:] if len(key) >= 12 else "…"
