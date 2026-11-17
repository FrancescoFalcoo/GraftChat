"""Set up and start GraftChat with one command: ``python start.py``.

What it does, each step only when needed:

1. checks the Python version (3.11 or newer);
2. creates a virtual environment in ``.venv`` and installs the backend into it
   (again only when ``pyproject.toml`` changes);
3. builds the frontend into ``web/dist`` when it is missing or older than its
   sources (this needs Node.js 20.19+ with npm; a release zip already contains
   the build, so it needs no Node);
4. starts the server on 127.0.0.1, on the first free port from 8000, and opens
   the browser. Settings then asks for your OpenRouter key.

Options: ``--fake`` (canned answers, no key, no network), ``--port N``,
``--no-browser``, ``--rebuild`` (build the frontend even if it looks current).
Standard library only: it runs before anything is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
WEB = ROOT / "web"
DIST_INDEX = WEB / "dist" / "index.html"
STAMP = VENV / ".graftchat-installed"
MIN_PYTHON = (3, 11)
MIN_NODE = (20, 19)


def say(message: str) -> None:
    print(f"[graftchat] {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n[graftchat] {message}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def run(command: list[str], cwd: Path = ROOT) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as error:
        fail(f"This step failed (exit code {error.returncode}): {' '.join(map(str, command))}")


# --- 1-2. Python and the backend ----------------------------------------------------------


def ensure_backend() -> Path:
    if sys.version_info < MIN_PYTHON:
        fail(
            f"GraftChat needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer; this is "
            f"{sys.version.split()[0]}. Install it from https://www.python.org/downloads/ "
            "and run this script with it."
        )
    python = venv_python()
    if not python.is_file():
        say("Creating the virtual environment in .venv...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    wanted = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if not STAMP.is_file() or STAMP.read_text(encoding="utf-8").strip() != wanted:
        say("Installing the backend (first run, or its dependencies changed)...")
        run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", "--quiet", "-e", ".[api]"])
        STAMP.write_text(wanted, encoding="utf-8")
    return python


# --- 3. The frontend -----------------------------------------------------------------------


def newest_source() -> float:
    newest = 0.0
    candidates = [WEB / "index.html", WEB / "package.json", WEB / "package-lock.json", WEB / "vite.config.ts"]
    candidates += [p for p in (WEB / "src").rglob("*") if p.is_file() and "test" not in p.parts]
    for path in candidates:
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest


def node_version(npm: str) -> tuple[int, int] | None:
    node = shutil.which("node")
    if node is None:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout
        major, minor, *_ = out.strip().lstrip("v").split(".")
        return int(major), int(minor)
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def ensure_frontend(rebuild: bool) -> None:
    built = DIST_INDEX.is_file()
    stale = built and (WEB / "src").is_dir() and newest_source() > DIST_INDEX.stat().st_mtime
    if built and not stale and not rebuild:
        return
    npm = shutil.which("npm")
    if npm is None:
        if built:
            say("The frontend build may be older than its sources, but npm is not installed: using it as it is.")
            return
        fail(
            "The interface has to be built once, and that needs Node.js "
            f"{MIN_NODE[0]}.{MIN_NODE[1]} or newer (https://nodejs.org). Install it and run this "
            "script again. Or download a release zip from GitHub (Releases): it comes with the "
            "interface already built and needs no Node."
        )
    version = node_version(npm)
    if version is not None and version < MIN_NODE:
        fail(f"Node.js {version[0]}.{version[1]} is too old: the build needs {MIN_NODE[0]}.{MIN_NODE[1]} or newer.")
    lock = WEB / "package-lock.json"
    installed = WEB / "node_modules" / ".package-lock.json"
    if not installed.is_file() or (lock.is_file() and lock.stat().st_mtime > installed.stat().st_mtime):
        say("Installing the frontend dependencies (npm ci)...")
        run([npm, "ci", "--no-audit", "--no-fund"], cwd=WEB)
    say("Building the interface (npm run build)...")
    run([npm, "run", "build"], cwd=WEB)


# --- 4. Start --------------------------------------------------------------------------------


def free_port(first: int, tries: int = 20) -> int:
    for port in range(first, first + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    fail(f"No free port between {first} and {first + tries - 1}. Choose one with --port.")
    raise AssertionError  # unreachable


def main() -> None:
    parser = argparse.ArgumentParser(prog="python start.py", description="Set up and start GraftChat.")
    parser.add_argument("--fake", action="store_true", help="canned answers: no key, no network, no cost")
    parser.add_argument("--port", type=int, default=None, help="port to use (default: first free from 8000)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--rebuild", action="store_true", help="build the frontend even if it looks current")
    args = parser.parse_args()

    python = ensure_backend()
    ensure_frontend(args.rebuild)

    port = args.port or free_port(int(os.environ.get("GRAFTCHAT_PORT") or 8000))
    env = dict(os.environ, GRAFTCHAT_PORT=str(port))
    if args.fake:
        env["GRAFTCHAT_FAKE_LLM"] = "1"
    command = [str(python), "-m", "api"] + ([] if args.no_browser else ["--open"])
    say(f"Starting on http://127.0.0.1:{port} (Ctrl+C to stop)...")
    try:
        sys.exit(subprocess.call(command, cwd=ROOT, env=env))
    except KeyboardInterrupt:
        say("Stopped.")


if __name__ == "__main__":
    main()
