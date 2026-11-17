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
``GRAFTCHAT_WEB_DIST``
    Folder of the built frontend to serve at ``/``. Default: ``web/dist``.
``OPENROUTER_API_KEY``
    If set, it wins over the key saved from the UI.

They can also be written in a ``.env`` file at the root of the repository (see
``.env.example``). A variable already set in the environment wins over the file.
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


def load_dotenv(path: Path) -> None:
    """Put the ``NAME=value`` lines of ``path`` into the environment, unless already set.

    Blank lines and ``#`` comments are skipped; values may be quoted. A missing file
    is not an error: ``.env`` is optional.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name and value and name not in os.environ:
            os.environ[name] = value


def load_config() -> Config:
    load_dotenv(REPO_ROOT / ".env")
    home = Path(os.environ.get("GRAFTCHAT_HOME") or Path.home() / ".graftchat")
    db_path = Path(os.environ.get("GRAFTCHAT_DB") or home / "graftchat.db")
    return Config(
        home=home,
        db_path=db_path,
        fake_llm=os.environ.get("GRAFTCHAT_FAKE_LLM", "") not in ("", "0"),
        web_dist=Path(os.environ.get("GRAFTCHAT_WEB_DIST") or REPO_ROOT / "web" / "dist"),
        port=int(os.environ.get("GRAFTCHAT_PORT") or 8000),
    )
