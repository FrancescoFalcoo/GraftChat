"""Live graphical preview of core/ in the browser.

Dev tool. Serves devtools/live.html and, at /api/state, the report of
``preview.py --json``, recomputed in a fresh process whenever a file in core/
(or the sample in preview.py) changes. The page polls /api/version and redraws.

    python devtools/live.py           # then open http://127.0.0.1:8765
    python devtools/live.py --open    # same, and open the default browser
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREVIEW = HERE / "preview.py"
PAGE = HERE / "live.html"
TIMEOUT_S = 10


def version() -> str:
    """Fingerprint of the watched files: changes whenever one is saved."""
    digest = hashlib.sha1()
    for path in sorted([*(ROOT / "core").rglob("*.py"), PREVIEW]):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        digest.update(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode())
    return digest.hexdigest()[:12]


def compute(current: str) -> bytes:
    """Run preview.py in a fresh process, so core/ is always re-imported."""
    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(PREVIEW), "--json"],
            cwd=ROOT, capture_output=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        report = {"fatal": {"title": f"preview.py non ha risposto entro {TIMEOUT_S} s: "
                                     "forse un ciclo infinito nel core?"}}
    else:
        try:
            report = json.loads(proc.stdout)
        except ValueError:
            report = {"fatal": {"title": "preview.py è terminato senza produrre dati",
                                "detail": proc.stderr.decode(errors="replace")[-3000:]}}
    report["version"] = current
    return json.dumps(report).encode()


class State:
    """Last report, recomputed only when the fingerprint changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version: str | None = None
        self._payload = b""

    def get(self) -> bytes:
        current = version()
        with self._lock:
            if current != self._version:
                self._payload = compute(current)
                self._version = current
            return self._payload


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send("text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/api/version":
            self._send("application/json", json.dumps({"version": version()}).encode())
        elif path == "/api/state":
            self._send("application/json", STATE.get())
        else:
            self._send("text/plain; charset=utf-8", b"not found", status=404)

    def _send(self, content_type: str, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass  # keep the terminal quiet: the page is the output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the default browser")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"GraftChat live preview: {url}   (Ctrl+C per fermare)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
