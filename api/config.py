"""Where things live on this computer, and the switches read from the environment.

Environment variables:

``GRAFTCHAT_HOME``
    Folder for the settings file and the database. Default: ``~/.graftchat``.
    It is outside the repository on purpose: the API key can never be committed.
``GRAFTCHAT_DB``
    Path of the SQLite file. Default: ``<GRAFTCHAT_HOME>/graftchat.db``.
``GRAFTCHAT_FAKE_LLM``
    ``1`` replaces OpenRouter with a canned local model (no key, no network).
    For UI work and demos.
``GRAFTCHAT_PORT``
    Port of ``python -m api``. Default: 8000.
``OPENROUTER_API_KEY``
    If set, it wins over the key saved from the UI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    home: Path
    db_path: Path
    fake_llm: bool
    web_dist: Path
    port: int

    @property
    def settings_path(self) -> Path:
        return self.home / "settings.json"


def load_config() -> Config:
    home = Path(os.environ.get("GRAFTCHAT_HOME") or Path.home() / ".graftchat")
    db_path = Path(os.environ.get("GRAFTCHAT_DB") or home / "graftchat.db")
    return Config(
        home=home,
        db_path=db_path,
        fake_llm=os.environ.get("GRAFTCHAT_FAKE_LLM", "") not in ("", "0"),
        web_dist=REPO_ROOT / "web" / "dist",
        port=int(os.environ.get("GRAFTCHAT_PORT") or 8000),
    )
