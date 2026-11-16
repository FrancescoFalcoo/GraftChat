"""``python -m api``: run the backend on this computer only (127.0.0.1).

``python -m api --open`` also opens the app in the default browser.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from api.app import create_app
from api.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m api", description="Run the GraftChat backend.")
    parser.add_argument("--open", action="store_true", help="open the app in the default browser")
    args = parser.parse_args()

    config = load_config()
    app = create_app(config=config)
    url = f"http://127.0.0.1:{config.port}"
    built = (config.web_dist / "index.html").is_file()

    print(f"GraftChat: {url}")
    if not built:
        print("  The frontend is not built: run 'npm install' and 'npm run build' in web/.")
    print(f"  Data folder: {config.home}")
    if config.fake_llm:
        print("  GRAFTCHAT_FAKE_LLM is on: answers are canned, no call leaves this computer.")
    if args.open:
        # After a moment, so the server is already listening when the page loads.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    # 127.0.0.1 on purpose: the API has no authentication and holds the user's key.
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="info")


if __name__ == "__main__":
    main()
