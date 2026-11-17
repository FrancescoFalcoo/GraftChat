# How `core/` works

A study guide to the code in `core/`: what each function does, why it is built that way and
where it is used. The rules come from [DESIGN.md](DESIGN.md) (mainly §6, §7 and §14); this
document holds the reasoning that connects them to the code.

To see everything at work on a sample conversation:

```bash
python devtools/preview.py     # calls every core function and prints the result
python -m pytest               # all the tests
```

## 1. The model in four sentences

- A **message** knows only the message before it in the same thread (`parent_id`). A thread
  is therefore a chain: root → child → child.
- **Main** is the thread with `branch_id = None`. Each **branch** is another thread, with its
  own `branch_id`. The first message of every thread has `parent_id = None` (§14.1).
- A branch is attached to main by a single piece of data: `anchor_message_id`, plus the
  offsets of the selected passage. The branch's messages hold no reference to main.
- When a branch comes back, a **merge node** (a message with role `merge`) appears on main
  and the branch stores its id in `merge_message_id`. **Take-away points** are separate
  rows, linked to the branch.
- A branch also stores its **base** (`base_message_id`): the last message of main when it
  was opened. It decides which merges the branch knows (§3, DESIGN §14.11).

Every function in `core/` is **pure**: it takes objects, returns new objects and touches
neither the database nor the network. Ids and timestamps are supplied by the caller. This is
why they can be tested without any setup.

## 2. `core/tree.py`

| Function | What it does |
|---|---|
| `thread` | Puts the messages of one thread in order, following the `parent_id` links. |
| `open_branch` | Creates an `OPEN` branch on `content[start:end]` of an answer on main, with its base. |
| `merge_branch` | Returns the branch marked `MERGED` at a merge node (§14.6). |
| `reusable_merge_node` | The merge node at the end of main a new merge can join, or `None` (§14.11). |
| `discard_branch` | Returns the branch marked `DISCARDED`. |
| `pending_branches` | The branches with no decision yet, i.e. the `OPEN` ones. |
| `check_invariants` | Checks the whole state of a conversation. |

A fix made to `merge_branch`: when main was empty, the error message read `main[-1]` and
Python raised `IndexError` instead of `InvariantError`. The last id is now read only when
main is not empty.

### `open_branch(anchor, start, end, *, new_id, created_at, base_message_id=None)`

Checks the anchor (an answer of the model, on main) and the offsets, copies the selected
text into `anchor_quote` and returns an `OPEN` branch. `base_message_id` is the last message
of main at that moment; the API passes it. `None` means "the anchor", which is how branches
stored before the field existed behave. Where the base sits on main is checked by
`check_invariants`, which sees the whole thread: `open_branch` sees only the anchor.

### `reusable_merge_node(messages, branches)`

Branches merged together share one merge node at the end of main (§14.6). This function says
whether a new merge can join the node that is there:

- main does not end on a merge node → `None` (a new node is needed);
- some branch has that node as its base → `None`. That branch was opened while the node was
  the end of main and sees every branch merged there; joining it now would show the branch
  a merge that happened after it was opened;
- otherwise → the node.

The API appends a new merge node when it gets `None`, so main may hold two merge nodes in a
row. For `_render` that is no special case: each node just adds its blocks to `pending`.

### `pending_branches(branches)`

Goes through the branches and keeps those with `status == OPEN`, in the order they arrive.
With the state machine of §14.5 (`OPEN → MERGED`, `OPEN → DISCARDED`, both final), "no
decision taken" and "`OPEN`" mean the same thing. Empty branches are included (§14.8): they
are still a pending decision, even if the only possible choice is to discard them.

The API uses it to tell the frontend how many branches to count in the banner "You came back
from N branches. Merge?".

### `check_invariants(messages, branches, points)`

The other functions check **one operation**. This one checks **everything that is stored**:
the API calls it before committing every change, and if it finds a violation the change is
rolled back. It returns nothing; it raises `InvariantError` at the first violation.

It runs in four steps, in this order:

1. `_check_unique_ids`: no repeated id among messages, among branches, among points. It
   comes first because the other checks build dictionaries keyed by id, and a dictionary
   silently overwrites a duplicate.
2. `_check_messages`:
   - everything belongs to a single conversation;
   - every message's `branch_id` exists. An "orphan" message would never be found by
     `thread`, because nobody asks for that branch;
   - merge nodes live on main only;
   - main and every branch are a single chain: calling `thread` is enough, since it already
     raises an error on two roots, a fork or an unreachable message.
3. `_check_branches`, for every branch:
   - the anchor exists, is on main, is an answer of the model, the offsets are inside the
     text and `anchor_quote` is exactly `content[start:end]`. These are the same rules as
     `open_branch`, checked again on the stored state. "Anchor on main" is the depth = 1
     rule;
   - `merge_message_id` is set **if and only if** the branch is `MERGED`;
   - when `base_message_id` is set: it is a message on main, not before the anchor;
   - if it is `MERGED`: the merge node exists, has role `merge` and is on main; the branch is
     not empty (§14.2); the merge node comes **after** the anchor on main, and after the
     base when there is one. These checks use each message's position in
     `thread(messages)`: a branch cannot come back before the point it started from.
4. `_check_points`: every point's branch exists, whatever its status (§14.9), and no two
   points of the same branch share a `position`.

What it does **not** check, and why:

- "`text_generated` is never overwritten" (§14.7). The function sees a snapshot of the
  state: it cannot know what was there before. The rule is enforced where a point is
  edited: the API can write only `included` and `text_final`.
- "From 1 to 6 points" and "titles of at most 5 words" (§8). These are requests made to the
  model that generates the take-aways, not properties of the data: `api/takeaway.py`
  enforces them.
- That the merge node is the end of main. That holds only at the moment of the merge
  (`merge_branch`); afterwards, main goes on.

## 3. `core/context.py`

Turns the stored tree into the list of messages the model actually receives. It is the piece
the experiment measures. The result is a `Context` holding a list of
`ContextMessage(role, content)`, where `role` is `user` or `assistant`. It never produces
`system` messages (§14.3). Each `ContextMessage` also has `source_id`, the id of the stored
message it renders (`None` for a message `_close` writes on its own). It is not part of
equality: two contexts with the same text are the same input. The API uses it to attach the
images of that message (DESIGN §14.12); `core` itself knows nothing about images.

### The two texts the app adds

`render_merge_block(anchor_quote, points)` writes the block of a merged branch:

```text
[merged from branch on: «Compress the images and serve them as WebP or AVIF»]
- Use AVIF for photos: at the same quality it is smaller than WebP.
- Fall back to WebP with <picture> for browsers without AVIF.
```

Only points with `included = True` appear, ordered by `position`, with their `text_final`
(the text as possibly edited by the user). When no point is checked it returns the empty
string: this is how a merge with no points "injects nothing" (§14.4).

`render_anchor_note(anchor_quote)` writes the sentence that tells the model which passage
the branch is about.

### The central idea: waiting blocks

A merge node is not a message for the model. It is a point on main where blocks "arrive".
Those blocks go **in front of the next user message**, each between the delimiters
`<context>` and `</context>` (§14.3, §14.10).

`_render` does exactly this, walking a thread already in order with a `pending` list of
waiting blocks:

| Message met | What happens |
|---|---|
| role `merge` | the blocks of the branches merged at that node are added to `pending` |
| role `user` | a `user` message goes out = waiting blocks + the user's text; `pending` is emptied |
| role `assistant` | an `assistant` message goes out, identical to the original |

Emptying `pending` after use is what guarantees that a block appears only once.

`_blocks_merged_at` picks the branches of a node: they must be `MERGED` and have a
`merge_message_id` equal to the node's id. It goes through them in id order, so the same
state always produces the same text (needed to repeat the experiment).

`_close` handles the edge case: if blocks are left at the end with no user message after
them (main ends on a merge node, or the branch is empty), they become a last `user` message
of their own. Dropping them would hide from the model something the user chose to bring
back.

### `build_main_context(messages, branches, points)`

Takes `thread(messages)`, i.e. main only, and passes it to `_render`. Branch messages never
enter: all that reaches main from a branch is the block of its checked points. `OPEN` and
`DISCARDED` branches contribute nothing.

Example. Main: a question, an answer, the merge node of branch 1, a new question. The model
receives three messages, and the last one is:

```text
<context>
[merged from branch on: «Compress the images and serve them as WebP or AVIF»]
- Use AVIF for photos: at the same quality it is smaller than WebP.
- Fall back to WebP with <picture> for browsers without AVIF.
</context>

Ok, what do I do first with the images?
```

### `build_branch_context(branch, messages, branches, points)`

Four steps, as in §7:

1. Main from the root up to and **including** the anchor, passed to `_render`. Take-aways
   merged before the anchor therefore propagate.
2. Main after the anchor, up to and including the **base**: only its merge nodes count, and
   each adds its blocks to `pending` (`_blocks_merged_at`). The user and assistant messages
   there are skipped. This is how a branch opened after a merge knows that merge's
   take-away, even when the merge came after the anchor (DESIGN §14.11). With no base, or a
   base equal to the anchor, the step does nothing.
3. The anchor note is added to `pending`, after those blocks: it will end up in front of the
   branch's first user message, right before what the user typed.
4. The branch's messages, passed to `_render` with empty lists of branches and points.

Example. Main: a question (1), an answer (2), the merge node (3) of a branch on answer 2.
A second branch is opened on answer 2 while main ends at 3, so its base is 3. Its first user
message reaches the model as:

```text
<context>
[merged from branch on: «First point.»]
- Merged fact.
</context>

<context>
The user is asking about this specific passage of your previous answer: «Second point.»
</context>

and this one?
```

**Isolation between siblings** comes from the construction, not from a filter: the function
reads main up to the base and the thread of that branch, so the messages of other branches
have no way in, and their take-aways only through merge nodes that existed when the branch
was opened. Nothing merged later can reach it, because `reusable_merge_node` never lets a
later merge join a node that is a base. If the anchor is not on main, or the base is not on
main after the anchor, it raises `InvariantError`.

## 4. Where the API calls the core

| When | Core function |
|---|---|
| every response carrying the conversation state | `thread`, `pending_branches` |
| the user selects a passage and opens a branch | `thread` (for the base), `open_branch` |
| the user writes on main / in a branch | `build_main_context` / `build_branch_context` |
| the user confirms the merge | `reusable_merge_node`, then `merge_branch` (once per branch, on the same merge node) |
| the user discards a branch | `discard_branch` |
| before committing any change to the database | `check_invariants` |

The code is in [api/service.py](../api/service.py): it loads the state from SQLite, calls the
core, calls the model and stores the result. It decides no rule.

## 5. Questions you are likely to get

**Why does the first message of a branch have `parent_id = None` and not the anchor?**
Because `parent_id` always means "previous message in the same thread". This way `thread`
treats main and branches the same way, with no special cases (§14.1).

**Why do the blocks go inside a user message and not in a `system` message?**
Some providers accept the system prompt only as a separate parameter, and `system` messages
in the middle of a conversation behave differently from one provider to another. A delimited
block inside the user message works everywhere (§14.3).

**Why does `merge_branch` receive all the messages?**
To check inside the core two rules that would otherwise end up in the API: an empty branch
cannot be merged, and the merge node must be the end of main (§14.6).

**What does the model receive if I merge a branch without checking anything?**
Nothing: `render_merge_block` returns the empty string and no block is created. In the data,
though, the branch stays `MERGED`, because it is needed for the history and for the
experiment (§14.4).

**Can a branch see another branch?**
Only through a merge that happened before the branch was opened: then it sees the points
brought back to main, as main sees them, whether the merge came before or after its anchor.
Never the other branch's messages, and never a merge made after it was opened.

**Why not let a branch see the whole of main up to its base?**
The anchor is what the branch is about; what main discussed after it may be another topic
and would only add noise. A take-away is different: the user chose to bring it back, so it is
part of what the conversation knows (DESIGN §14.11).

**How much does building a context cost?**
It is linear in the number of messages, times the number of branches whenever a merge node is
met. At the size of a chat it is negligible; the model call costs orders of magnitude more.

**How do I know the app sends the model exactly what the core builds?**
Every call is stored in `llm_call_log.prompt_json` with the exact messages, and the backend
tests compare that text with the output of `core.context`.
