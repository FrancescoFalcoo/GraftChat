# GraftChat

Anchored branching chat for LLMs: graft side conversations onto any passage of an answer,
then bring back only what matters.

LLM chats are linear. When an answer has several points and you want to dig into two of them
separately, every follow-up lands at the bottom, the sub-discussions mix, and every tangent
stays in the model's context forever. GraftChat lets you:

1. chat normally on a **main** thread;
2. select a passage of any answer and open a **branch** anchored to it, in a side panel;
3. back on main, **merge**: the model writes a take-away of short points for each branch and
   you tick which ones enter the main context. Everything else stays out.

The design, the research question behind it and every decision are in
[docs/DESIGN.md](docs/DESIGN.md).

## Status

Work in progress (v1). `api/` and `web/` are complete; part of `core/` (the context builder
and the whole-state checks) is still being written. Until then the app starts, and tells you
which core functions are missing, but chatting returns an error.

## Run it

Requirements: Python 3.11+, Node 20+.

```bash
# once
python -m venv .venv && .venv/Scripts/activate      # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cd web && npm install && npm run build && cd ..

# every time
python -m api                                       # open http://127.0.0.1:8000
```

On first start, Settings asks for an [OpenRouter](https://openrouter.ai) API key, a monthly
spend cap and a model (the list shows OpenRouter's free models). The key is stored in
`~/.graftchat/settings.json` on your computer, never in this repository, and is sent only to
OpenRouter.

To try the interface without a key or network: `GRAFTCHAT_FAKE_LLM=1 python -m api` (canned
answers).

### Development

```bash
python -m api                 # backend on :8000
cd web && npm run dev         # frontend on :5173, proxies /api to the backend

python -m pytest              # core + backend tests
cd web && npm test            # frontend tests
```

## Layout

| folder | what | docs |
|---|---|---|
| `core/` | data model, tree rules and invariants, context builder. No dependencies, no I/O. | [DESIGN.md](docs/DESIGN.md) |
| `api/` | FastAPI backend: SQLite, OpenRouter client, take-away generation, spend cap, logging | [api/README.md](api/README.md), [docs/API.md](docs/API.md) |
| `web/` | React + TypeScript frontend: chat, branch side panel, merge checklist | [web/README.md](web/README.md) |
| `experiments/` | experiment runner and evaluation (DESIGN §11) | – |
| `tests/` | unit tests for `core/`; `tests/backend/` for `api/` | – |
| `devtools/` | live preview of `core/` while developing it | – |
