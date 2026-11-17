# api/

FastAPI backend (DESIGN.md §9, §12): HTTP endpoints, SQLite persistence and migrations,
OpenRouter client with retries, take-away generation, spend cap, LLM call logging.

It contains **no tree logic**: every rule is decided by `core.tree` and every model input
is built by `core.context`. The HTTP contract is in [docs/API.md](../docs/API.md).

## Run

```bash
pip install -e ".[dev]"      # once
python -m api                # http://127.0.0.1:8000
```

If `web/dist` exists (`npm run build` in `web/`), the same process serves the frontend at `/`.
During frontend development run `npm run dev` in `web/` instead: Vite proxies `/api` here.

| variable | meaning | default |
|---|---|---|
| `GRAFTCHAT_HOME` | folder of `settings.json` and the database | `~/.graftchat` |
| `GRAFTCHAT_DB` | SQLite file | `<home>/graftchat.db` |
| `GRAFTCHAT_PORT` | port | `8000` |
| `GRAFTCHAT_FAKE_LLM` | `1` = canned local answers, no key, no network | off |
| `OPENROUTER_API_KEY` | overrides the key saved from the UI | – |

The server binds to `127.0.0.1` only: it has no authentication and it holds the API key.

## Files

| file | role |
|---|---|
| `app.py` | routes, request validation, the `{error: {code, message}}` format |
| `service.py` | use cases: load state → call `core` → call the provider → store |
| `db.py`, `migrations/` | SQLite: schema of DESIGN §6, rows ⇄ `core.models` dataclasses |
| `provider.py` | OpenRouter client (retries, error mapping), free-model list, `FakeProvider` |
| `takeaway.py` | take-away prompt and tolerant JSON parsing (DESIGN §8) |
| `settings.py` | API key, spend cap, chosen models, in `settings.json` |
| `corestatus.py` | which `core` functions are still stubs (`GET /api/health`) |
| `config.py` | paths and environment switches |

## Behaviour worth knowing

- **Core stubs.** A `core` function that still raises `NotImplementedError` becomes an HTTP 501
  naming the function; `GET /api/health` lists all of them.
- **API key.** Stored in `settings.json` under `GRAFTCHAT_HOME`, outside the repository. Never
  returned by the API (only a 4-character hint), never written to the database or the logs.
- **Spend cap.** Checked before every model call against the sum of `cost_estimate` in
  `llm_call_log` for the current calendar month (UTC). With a positive cap, calls stop once the
  month's spend reaches it. With cap `0` ("free models only"), calls stop as soon as anything at
  all has been spent. The cost of a call is known only after it returns, so the cap can be
  overshot by at most one call. `cost_estimate` is what OpenRouter reports in `usage.cost`
  (0 when it reports nothing).
- **Logging.** Every successful model call is one row of `llm_call_log`, with the exact
  messages sent (`prompt_json`). Failed calls produce no row.
- **Failures.** A provider failure after the user message was stored leaves that message as
  the last of its thread; the UI offers retry or delete (see docs/API.md, "Chat").
- **Images.** Stored in the `attachment` table (bytes in SQLite), served by
  `GET /api/attachments/{id}`, sent to OpenRouter as base64 data URLs with the message they
  belong to, logged as `attachment:<id>`. The type is sniffed from the bytes; only PNG, JPEG,
  GIF and WebP are accepted, so the route never serves HTML or SVG. Whether the chosen model
  takes images comes from OpenRouter's model list (`architecture.input_modalities`).
- **Merge nodes.** A merge joins the merge node at the end of main only if no branch was
  opened from it since (`core.tree.reusable_merge_node`, DESIGN §14.11); otherwise a new node
  is appended.
- **Migrations.** `migrations/NNNN_name.sql`, applied in order at startup, tracked with
  `PRAGMA user_version`. Add a new numbered file; never edit an applied one.

## Tests

```bash
python -m pytest tests/backend
```

They run the API on the real `core` against a scripted provider: no network, no key.
