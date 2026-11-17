# GraftChat

[![CI](https://github.com/FrancescoFalcoo/GraftChat/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancescoFalcoo/GraftChat/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Anchored branching chat for LLMs.** Graft a side conversation onto any passage of an
answer, then bring back only what matters.

## The problem

LLM chats are linear. When an answer has several points and you want to dig into two of them
separately, every follow-up lands at the bottom of the conversation: the original answer
drifts away, the sub-discussions mix, and every tangent stays in the model's context forever.

## How it works

1. **Chat** normally on a main thread.
2. **Branch:** select a passage of any answer. A side panel opens a conversation anchored to
   that passage, isolated from the other open branches. It already knows the take-aways you
   merged before opening it, so a second branch on the same answer builds on the first.
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

You can also attach files to a message (paste, drop or the clip button). Images reach models
that accept them, marked "images" in Settings. PDFs, Word files and text or code files are read
to text on your computer and work with every model.

## Quick start

You need **Python 3.11+** and, to build the interface the first time, **Node.js 20.19+**
([python.org](https://www.python.org/downloads/), [nodejs.org](https://nodejs.org)).

```bash
git clone https://github.com/FrancescoFalcoo/GraftChat.git
cd GraftChat
python start.py
```

That is all. `start.py` creates a virtual environment in `.venv`, installs the backend, builds
the interface, starts the server on `127.0.0.1` and opens your browser. Later runs skip what is
already done, so `python start.py` is also how you start it every day. (On macOS and Linux
the command may be `python3`.)

No Node? Download the zip of the latest [release](https://github.com/FrancescoFalcoo/GraftChat/releases)
instead of cloning: it contains the interface already built, so `python start.py` needs only
Python.

### Your key

On the first start, Settings opens and asks for an [OpenRouter](https://openrouter.ai) key:

- **Connect OpenRouter:** log in on OpenRouter and approve; you come back with a key, saved on
  your computer. Nothing to copy.
- **Or paste a key** made at [openrouter.ai/keys](https://openrouter.ai/keys). It is checked
  with OpenRouter before it is saved.

A good free model is already selected. Free models cost nothing; without credits on your
OpenRouter account they allow **50 requests a day** (one per message, one or two more per
take-away). Buying 10 credits once raises that to 1,000 a day. The spend cap starts at 0, which
means free models only.

### Options

```bash
python start.py --fake          # canned answers: try the interface with no key and no network
python start.py --port 8100     # another port (by default the first free one from 8000)
python start.py --no-browser    # do not open the browser
```

The key can also live in a `.env` file at the root (copy [.env.example](.env.example)); a key
set there or in `OPENROUTER_API_KEY` wins over the one saved from the UI.

### If something goes wrong

| What you see | What to do |
|---|---|
| "needs Python 3.11 or newer" | Install a newer Python and run `start.py` with it (`py -3.12 start.py` on Windows). |
| "that needs Node.js" | Install Node.js 20.19+ and run it again, or use a release zip. |
| "rate limited" or "50 requests" in an error | The daily free-model quota is used up: wait until tomorrow (UTC) or add credits on OpenRouter. |
| "does not accept images" | Choose a model marked "images" in Settings. |
| A model stops answering | Free models come and go on OpenRouter: pick another in Settings. |

## Privacy and cost

- **Your key stays on your computer.** It is saved in `~/.graftchat/settings.json`, outside
  this repository, and is sent only to OpenRouter. The server listens on `127.0.0.1` only and refuses requests
  coming from other websites open in the same browser.
- **Spend cap.** Before every model call the app adds up what the month has cost so far and
  refuses the call once the cap is reached. A cap of 0 means free models only.
- **Everything is logged locally.** Each model call is stored in a local SQLite database
  with the exact messages that were sent, so what the model saw can always be checked.
  Attached files are stored in the same database and sent only to OpenRouter; documents are
  read to text locally, and the log shows that text exactly as the model received it.

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
| [`start.py`](start.py) | One-command setup and start (venv, install, build, run). |

Documentation:

- [docs/DESIGN.md](docs/DESIGN.md): the design, its scope and every decision taken along the way.
- [docs/CORE.md](docs/CORE.md): how the core works, function by function.
- [docs/API.md](docs/API.md): the HTTP contract between backend and frontend.
- [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md): proposal for letting other people try it with their own key.
- [docs/CONTEXT.md](docs/CONTEXT.md): design for a per-model length meter and deep summaries of old messages.
- [api/README.md](api/README.md) and [web/README.md](web/README.md): notes for each part.

## Development

```bash
pip install -e ".[dev]"           # in the venv: the backend plus the test tools
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
past messages, scanned PDFs (no OCR). The backlog is in [DESIGN.md §10](docs/DESIGN.md#10-v2-backlog).

## License

[MIT](LICENSE) © 2026 Francesco Falco
