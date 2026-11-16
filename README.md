# GraftChat

[![CI](https://github.com/FrancescoFalcoo/GraftChat/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancescoFalcoo/GraftChat/actions/workflows/ci.yml)

**Anchored branching chat for LLMs.** Graft a side conversation onto any passage of an
answer, then bring back only what matters.

## The problem

LLM chats are linear. When an answer has several points and you want to dig into two of them
separately, every follow-up lands at the bottom of the conversation: the original answer
drifts away, the sub-discussions mix, and every tangent stays in the model's context forever.

## How it works

1. **Chat** normally on a main thread.
2. **Branch:** select a passage of any answer. A side panel opens a conversation anchored to
   that passage, isolated from the other branches.
3. **Merge:** back on main, the model writes a take-away of short points for each branch.
   You tick the points that should return to the main context, edit them if you want, and
   discard the branches that led nowhere.

The rule behind it: **no hidden state**. After a merge the model receives exactly the points
you ticked, in front of your next message, and nothing else from the branch:

```text
<context>
[merged from branch on: «Compress the images and serve them as WebP or AVIF»]
- Use AVIF for photos: at the same quality it is smaller than WebP.
- Fall back to WebP with <picture> for browsers without AVIF.
</context>

Ok, what do I do first with the images?
```

A branch that is never merged contributes nothing.

## Quick start

Requirements: Python 3.11+ and Node 20.19+.

```bash
git clone https://github.com/FrancescoFalcoo/GraftChat.git
cd GraftChat

python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

cd web && npm install && npm run build && cd ..

python -m api                     # then open http://127.0.0.1:8000
```

On first start, Settings asks for an [OpenRouter](https://openrouter.ai) API key, a monthly
spend cap and a model (the list shows OpenRouter's free models).

To look around without a key or a network connection, start it with canned answers:

```bash
GRAFTCHAT_FAKE_LLM=1 python -m api          # PowerShell: $env:GRAFTCHAT_FAKE_LLM=1; python -m api
```

## Privacy and cost

- **Your key stays on your computer.** It is saved in `~/.graftchat/settings.json`, outside
  this repository, and is sent only to OpenRouter. The server listens on `127.0.0.1` only.
- **Spend cap.** Before every model call the app adds up what the month has cost so far and
  refuses the call once the cap is reached. A cap of 0 means free models only.
- **Everything is logged locally.** Each model call is stored in a local SQLite database
  with the exact messages that were sent, so what the model saw can always be checked.

## Research question

GraftChat is also the test bench for one question: *when you return to the main thread after
one or more branches, what should the model receive?*

| Condition | What main sees of each branch |
|---|---|
| A. Linear baseline | The branch exchanges, appended to main in chronological order |
| B. Full | The full branch messages, inserted at the merge point |
| C. Take-away | Only the generated take-away points |
| D. Excluded | Nothing |

The experiment compares input tokens, the quality of the next answer on main, and
contamination (branch content leaking where it should not). It has not been run yet; the plan
is in [DESIGN.md §11](docs/DESIGN.md#11-experiment-after-v1).

## Project layout

| Folder | What it holds |
|---|---|
| [`core/`](core/) | Data model, tree rules and invariants, context builder. Pure Python, no dependencies, no I/O. |
| [`api/`](api/) | FastAPI backend: SQLite, OpenRouter client with retries, take-away generation, spend cap, call log. |
| [`web/`](web/) | React + TypeScript frontend: chat, branch side panel, merge checklist. |
| [`tests/`](tests/) | Unit tests for `core/`; integration tests for `api/` in `tests/backend/`. |
| [`experiments/`](experiments/) | Experiment runner and evaluation (not started). |
| [`devtools/`](devtools/) | Live preview of `core/` on a sample conversation. |

Documentation:

- [docs/DESIGN.md](docs/DESIGN.md): the design, its scope and every decision taken along the way.
- [docs/CORE.md](docs/CORE.md): how the core works, function by function (in Italian).
- [docs/API.md](docs/API.md): the HTTP contract between backend and frontend.
- [api/README.md](api/README.md) and [web/README.md](web/README.md): notes for each part.

## Development

```bash
python -m api                     # backend on http://127.0.0.1:8000
cd web && npm run dev             # frontend on http://127.0.0.1:5173, proxies /api to the backend

python -m pytest                  # core and backend tests
cd web && npm test                # frontend tests
python devtools/preview.py        # what every core function returns on a sample conversation
```

## Status

v1 is feature-complete: chat, branches, merge with take-aways, bring-your-own-key, spend cap
and call logging all work end to end. Next comes the experiment.

Out of scope for v1, by design: branches of branches, streaming, several providers, editing
past messages. The backlog is in [DESIGN.md §10](docs/DESIGN.md#10-v2-backlog).
