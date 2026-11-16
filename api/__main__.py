"""``python -m api``: run the backend on this computer only (127.0.0.1)."""

from __future__ import annotations

import uvicorn

from api.app import create_app
from api.config import load_config


def main() -> None:
    config = load_config()
    app = create_app(config=config)
    served = "with the built frontend" if (config.web_dist / "index.html").is_file() else "API only"
    print(f"GraftChat: http://127.0.0.1:{config.port}  ({served})")
    print(f"  data folder: {config.home}")
    if config.fake_llm:
        print("  GRAFTCHAT_FAKE_LLM is on: answers are canned, no call leaves this computer.")
    # 127.0.0.1 on purpose: the API has no authentication and holds the user's key.
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="info")


if __name__ == "__main__":
    main()
