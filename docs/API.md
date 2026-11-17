# GraftChat HTTP API

Contract between `api/` (FastAPI) and `web/` (React). Everything is JSON under `/api`.
The server listens on `127.0.0.1` only. Rules and vocabulary come from [DESIGN.md](DESIGN.md).

## Conventions

- Ids are integers. Timestamps are ISO-8601 UTC strings.
- **Offsets are Python string offsets (Unicode code points), not UTF-16 units.** The
  frontend converts DOM offsets before sending them.
- Every error has the same body, with an HTTP status ≥ 400:

```json
{ "error": { "code": "spend_cap_reached", "message": "Human-readable text." } }
```

| code | status | meaning |
|---|---|---|
| `not_found` | 404 | conversation, branch, message or point does not exist |
| `validation` | 422 | malformed request (empty content, bad offsets, quote mismatch…) |
| `invariant` | 409 | a `core.tree` rule refused the operation (`InvariantError`) |
| `conflict` | 409 | wrong state for the operation (branch not open, thread awaiting a reply, generation already running…) |
| `core_not_implemented` | 501 | a `core/` function still raises `NotImplementedError`; the message names it |
| `no_api_key` | 400 | no OpenRouter key configured |
| `no_model` | 400 | no model chosen in the settings |
| `spend_cap_reached` | 402 | monthly spend cap reached, no call was made |
| `provider_auth` | 502 | OpenRouter rejected the key |
| `provider_rate_limit` | 502 | rate limited after retries |
| `provider_error` | 502 | any other provider failure (after retries) |
| `takeaway_parse` | 502 | the model did not return a usable take-away |

Images: a `validation` error is also returned for a bad image (wrong type, too large, too
many, not base64) and when the chosen model is known not to accept images.

## Shapes

```ts
type Role = "user" | "assistant" | "merge";
type BranchStatus = "open" | "merged" | "discarded";

interface Attachment {
  id: number;
  kind: "image";
  mime: string;               // image/png | image/jpeg | image/gif | image/webp (from the bytes)
  name: string;
  size: number;               // bytes
}

interface Message {
  id: number;
  branch_id: number | null;   // null = main
  parent_id: number | null;
  role: Role;
  content: string;            // "" for merge nodes; may be "" for a user message with images
  created_at: string;
  attachments: Attachment[];  // [] except on user messages sent with images
}

interface Point {
  id: number;
  branch_id: number;
  position: number;
  title: string;
  text_generated: string;     // never changes
  text_final: string;         // what enters the context
  included: boolean;
}

interface Branch {
  id: number;
  anchor_message_id: number;
  anchor_start: number;       // code points
  anchor_end: number;
  anchor_quote: string;
  status: BranchStatus;
  merge_message_id: number | null;
  base_message_id: number | null; // last message of main when the branch was opened (DESIGN §14.11);
                                  // null for branches stored before it existed (= the anchor)
  created_at: string;
  messages: Message[];        // the branch thread, in order (may be empty)
  points: Point[];            // ordered by position; [] until a take-away is generated
}

interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  open_branches: number;
}

interface ConversationState {
  conversation: { id: number; title: string; created_at: string };
  main: Message[];            // the main thread, in order, merge nodes included
  branches: Branch[];         // ordered by creation
  pending_branch_ids: number[] | null; // null while core.tree.pending_branches is not implemented
}

interface Settings {
  has_api_key: boolean;
  api_key_hint: string | null;     // e.g. "…a1b2", never the key itself
  api_key_from_env: boolean;       // true when OPENROUTER_API_KEY is set (the UI cannot change it)
  spend_cap_usd: number;           // 0 = free models only
  chat_model: string | null;
  takeaway_model: string | null;   // null = use chat_model
  month_spend_usd: number;         // sum of cost_estimate this calendar month (UTC)
  fake_llm: boolean;               // true when the server runs with GRAFTCHAT_FAKE_LLM=1
}

interface Health {
  ok: true;
  core: Record<string, boolean>;   // "core.tree.pending_branches": false = still a stub
}

interface Model { id: string; name: string; context_length: number | null; images: boolean }
```

## Endpoints

### Health and settings

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/health` | – | `Health` |
| GET | `/api/settings` | – | `Settings` |
| PUT | `/api/settings` | any subset of `{ api_key, spend_cap_usd, chat_model, takeaway_model }` | `Settings` |
| DELETE | `/api/settings/api-key` | – | `Settings` |
| GET | `/api/models` | – | `{ models: Model[] }` — free OpenRouter models; `provider_error` if the list cannot be fetched |

`api_key: ""` is rejected (`validation`); use DELETE to remove the key.
`takeaway_model: null` clears it.

### Conversations

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/conversations` | – | `{ conversations: ConversationSummary[] }`, newest first |
| POST | `/api/conversations` | `{ title?: string }` | `ConversationState` (201) |
| GET | `/api/conversations/{id}` | – | `ConversationState` |
| PATCH | `/api/conversations/{id}` | `{ title: string }` | `ConversationState` |

A conversation created without a title is called "New chat" and is renamed after its
first user message.

### Chat

| method | path | body | returns |
|---|---|---|---|
| POST | `/api/conversations/{id}/messages` | `{ content: string, branch_id?: number \| null, images?: ImageIn[] }` | `ConversationState` |
| POST | `/api/conversations/{id}/generate` | `{ branch_id?: number \| null }` | `ConversationState` |
| DELETE | `/api/messages/{id}` | – | `ConversationState` |
| GET | `/api/attachments/{id}` | – | the image bytes, with its MIME type |

```ts
interface ImageIn { name: string; mime?: string; data: string } // data: base64, no "data:" prefix
```

**Images.** Up to 4 per message, 5 MB each, PNG, JPEG, GIF or WebP. The type is recognised
from the bytes (`mime` is informative). `content` may be empty when there are images. The
images are stored with the user message and sent to the model with it every time that
message is part of a context, as OpenAI-style `image_url` parts with base64 data URLs; the
call log records them as `attachment:<id>`. If the chosen model appears in OpenRouter's list
as not accepting images, a message with images is refused (`validation`) before anything is
stored, and images already in the history are replaced by the note
`[image not sent: the selected model does not accept images]`. A model typed by hand, or a
list that cannot be fetched, counts as unknown: the images are sent and the provider decides.

`POST …/messages` stores the user message, calls the model and stores the reply.

- Nothing is stored when the request is refused before the model call (`validation`,
  `conflict`, `no_api_key`, `no_model`, `spend_cap_reached`, `core_not_implemented`).
- If the **provider** fails (`provider_*`), the user message **stays** as the last message
  of its thread. The thread is then "awaiting a reply": a new `POST …/messages` on it
  returns `conflict`. The UI offers two ways out:
  - `POST …/generate` retries the model call for a thread that ends with a user message;
  - `DELETE /api/messages/{id}` removes that dangling user message (only allowed for a
    user message that is the last of its thread).
- Chatting is only possible in an `open` branch (`conflict` otherwise).
- Two generations on the same thread at once: the second gets `conflict`.

### Branches

| method | path | body | returns |
|---|---|---|---|
| POST | `/api/conversations/{id}/branches` | `{ anchor_message_id, start, end, quote }` | `{ branch_id: number, state: ConversationState }` (201) |
| POST | `/api/branches/{id}/discard` | – | `ConversationState` |
| POST | `/api/branches/{id}/takeaway` | `{ regenerate?: boolean }` | `ConversationState` |
| PATCH | `/api/points/{id}` | any subset of `{ included: boolean, text_final: string }` | `ConversationState` |
| POST | `/api/conversations/{id}/merge` | `{ branch_ids: number[] }` | `ConversationState` |

- **Open**: `quote` is the selected text as the frontend sees it; the server checks it
  equals `content[start:end]` and answers `validation` if not (this catches offset
  conversion bugs). The anchor must be an assistant message on main (`invariant`).
- **Take-away**: generates the points of an open, non-empty branch and caches them. A
  second call returns the cached points without calling the model. `regenerate: true`
  replaces them (explicit user action; only while the branch is open). New points are
  all `included: true`.
- **Points**: can only be changed while their branch is open. `text_final` must not be
  blank. `text_generated` cannot be changed.
- **Merge**: merges the listed branches at the current end of main. Each must be open,
  non-empty and have a generated take-away (`conflict` otherwise); main must not be
  awaiting a reply. The server appends one `merge` message to main (or reuses the last
  message of main if it is already a merge node and no branch was opened from it since,
  `core.tree.reusable_merge_node`) and marks the branches as merged there. Zero checked
  points is valid (DESIGN §14.4).
- **Open** also records `base_message_id`, the current last message of main: the branch
  sees the take-aways merged up to there, even after its anchor (DESIGN §14.11).
- **Discard**: only an open branch (`invariant` otherwise). Empty branches can be discarded.
