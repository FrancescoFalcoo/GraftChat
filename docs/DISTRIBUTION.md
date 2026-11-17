# Letting other people try GraftChat

**Status:** proposal, 2026-11-17. Done since: `python start.py` (one command from a clone,
step 1 without PyPI), release zips with the interface built (no Node needed), "Connect
OpenRouter" (step 2) and the key check. Still open: PyPI, single-file builds, steps 3 and 4.

The goal: other people can try GraftChat with their own OpenRouter key, with as little setup
as possible, without the author paying for their calls or holding their keys, and, if they
agree, contributing data to the experiment (DESIGN §11).

## 1. Where we start from

- The app is local: one Python process (`python -m api`) serves the API and the built
  frontend on `127.0.0.1`, with no authentication. That is safe only because nobody else can
  reach it: other computers cannot connect, and web pages open in the same browser are
  refused by the `Host` and `Origin` checks (docs/API.md, `not_local`).
- The key is BYOK already: pasted in Settings, stored in `~/.graftchat/settings.json`, sent
  only to OpenRouter. The spend cap and the call log are local too.
- Installing it today needs git, Python 3.11+, Node 20 and four commands. That is fine for a
  developer and too much for most testers.
- The wheel built from `pyproject.toml` contains `core/` and `api/` but **not** `web/dist`
  (`api/config.py` looks for it next to the repository), so `pip install graftchat` would
  give a server without its interface.

Facts about OpenRouter this proposal relies on (checked 2026-11-17 on openrouter.ai/docs):

- **OAuth PKCE.** An app can send the user to `https://openrouter.ai/auth?callback_url=…&code_challenge=…&code_challenge_method=S256`; the user logs in and approves; the app exchanges the returned `code` for a key with `POST https://openrouter.ai/api/v1/auth/keys`. Callbacks on `http://localhost:<any port>` are allowed. The key spends the user's own credits until they revoke it. The user never copies a key by hand.
- **Free-model limits.** 20 requests per minute, and 50 requests per day for accounts that have bought less than 10 credits in total (1,000 per day from 10 credits). One message costs one request, and a take-away one or two more, so a tester with no credits gets roughly 30–40 messages a day. The first-run screen should say so.

## 2. Options

| | A. Local app, easy install | B. Hosted, the key stays in the browser | C. Hosted, multi-user server |
|---|---|---|---|
| What the tester does | install one package or download one file, run it | open a URL | open a URL, sign in |
| Where data lives | their computer (SQLite) | their browser (IndexedDB) | the author's server |
| Who holds the key | their computer | their browser | the author's server (encrypted) |
| Who pays for hosting | nobody | static hosting, free | a server and a database |
| Work needed | packaging | port `core/` to the browser, rewrite `api/` as client code | accounts, per-user data, key encryption, rate limits, privacy policy, operations |
| Fits "no hidden state" and "the key never leaves your computer" | yes, as today | yes | no: the key passes through a third party |

**C is out for now.** It turns a research prototype into a service that holds other people's
credentials, with the security and legal work that comes with it, for no gain over B.

**B is attractive later.** `core/` is pure Python with no dependencies, so it could run
unchanged in the browser through Pyodide, or be ported to TypeScript (about 400 lines,
already specified by its tests). OpenRouter accepts calls from the browser. But `api/` would
have to be rewritten as client code, and the experiment runner wants the Python `core/`.
Two copies of the core would drift.

**A is the recommendation for the first round of testers.** It changes nothing in the
architecture and keeps every promise the README makes.

## 3. Proposed plan

### Step 1: one command to run it

1. **Ship the frontend inside the package.** Build `web/` in CI and copy `web/dist` into
   `api/web/` before building the wheel (package data). `config.web_dist` looks there first,
   then in the repository, as today.
2. **A `graftchat` command** (`[project.scripts]`), the same as `python -m api`, that also
   opens the browser on start and picks a free port if 8000 is taken.
3. **Publish to PyPI.** Testers then run one of:

   ```bash
   uvx graftchat           # with uv: nothing to install first
   pipx run graftchat      # with pipx
   ```

   Both need Python. For people without it, a later step can add single-file builds
   (PyInstaller, one per OS, attached to GitHub releases), or a Docker image for those who
   prefer it.
4. **Version check.** A line in Settings when a newer release exists (read from PyPI, no
   telemetry).

### Step 2: connect a key without copying it

Add a "Connect OpenRouter" button to the first-run screen, using OAuth PKCE with the
callback on the local server (`http://127.0.0.1:<port>/api/oauth/callback`). The server
generates the verifier, exchanges the code and saves the key exactly where a pasted key goes
today. Pasting a key stays possible. The first-run screen also says what free models allow
per day (§1), and that a key with credits can call paid models, which is what the spend cap
is for.

### Step 3: data for the experiment, opt-in only

The experiment (DESIGN §11) needs real conversations with branches. Testers' data never
leaves their computer unless they choose to send it:

- **"Export for research"** in Settings writes one JSON file: the structure of the selected
  conversations (messages, branches, points, merge decisions, token counts from the call log),
  with the option to replace every text with its length. No key, no images.
- The tester sends the file themselves (an email or an issue form). There is no upload
  endpoint, so there is no server to secure.
- The export format is versioned and documented, so the runner in `experiments/` can read it.

Interesting signals for the research question, all already in the database: how many points
people untick or edit (`included`, `text_final` vs `text_generated`), how often they discard
branches, how many branches they open per answer.

### Step 4: feedback

A "Send feedback" link to a GitHub issue template (what they tried, what confused them, which
model). Since testers are few, this is enough; no analytics.

## 4. Open questions

1. **Who are the first testers?** Developers can live with `uvx`; others need step 1.3's
   single-file builds first.
2. **Default model.** Free models come and go, and some do not accept images. Ship a short
   list of known-good defaults and update it with each release, or always pick from the live
   list?
3. **Is the research export worth anonymising further?** Replacing texts with lengths loses
   what the LLM judge needs. A middle way: the tester picks which conversations to share in
   full.
4. **When to reconsider B.** If testers ask for "just a link", B becomes worth its cost. The
   decision to make then: Pyodide (one core, a heavier page) or a TypeScript port (a light
   page, two cores kept in step by shared test cases).
