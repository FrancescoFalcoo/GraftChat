# Contributing

Thanks for your interest in GraftChat. It is a personal research project, so a few things
work differently from a typical open-source repository: please read this before opening a
pull request.

## Bugs and ideas

- **Bugs:** open an issue with the "Bug report" form. Say what you did, what you expected and
  what happened, plus your operating system, the GraftChat version and the model you used.
- **Ideas:** open an issue with the "Idea" form. Check the
  [v2 backlog](docs/DESIGN.md#10-v2-backlog) first: it may already be planned.
- **Security problems:** never in a public issue; see [SECURITY.md](SECURITY.md).

## Who decides what

The project is split in two areas ([DESIGN.md §9](docs/DESIGN.md#9-ownership)):

- **`core/` and `experiments/`** belong to the author: the tree model and its rules, the
  context builder, the merge logic and the experiment. The research question depends on them,
  so changes there are made by the author. Issues that point out a bug or propose an idea
  are very welcome; pull requests that change them will usually be closed with thanks, and the
  idea taken from there.
- **`api/`, `web/` and everything else** are open to pull requests.

For anything larger than a small fix, open an issue first so we can agree on the approach.

## Setting up

You need Python 3.11+ and Node.js 20.19+.

```bash
git clone https://github.com/FrancescoFalcoo/GraftChat.git
cd GraftChat
python start.py --fake            # the whole app with canned answers: no key, no network
```

For development, with automatic reload of the interface:

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
GRAFTCHAT_FAKE_LLM=1 python -m api                # backend on http://127.0.0.1:8000
cd web && npm ci && npm run dev                  # interface on http://127.0.0.1:5173
```

## Before you open a pull request

```bash
python -m pytest                  # core and backend tests
cd web && npm test                # interface tests
cd web && npx tsc --noEmit        # type check
```

- Add a test for what you change: every behaviour has one.
- If you change an HTTP route or its JSON, update [docs/API.md](docs/API.md) in the same pull
  request; if you change a rule or a decision, the relevant section of
  [docs/DESIGN.md](docs/DESIGN.md).
- Keep the rule of the project: **no hidden state**. What the model receives must always be
  exactly what the user can see and check.
- Never commit an API key, a `.env` file or a database.

## Commit messages

One change per commit, in this form:

```text
[WORK] area: what changed and why
[FIX] area: what was broken and how it is fixed
```

`area` is `core`, `api`, `web`, `docs`, `repo`, `release` and so on. Examples from the history:

```text
[FIX] api: answer only this computer's own pages; a foreign Host ... is refused with 403 not_local
[WORK] web: Show tokens and cost (Settings, off by default) ...
```

## License

By contributing you agree that your contribution is released under the [MIT License](LICENSE).
