# GraftChat — Design

Anchored branching chat for LLMs: graft side conversations onto any passage of an answer, then bring back only what matters.

**Status:** v1 implemented (milestones 1–4 of §13). The v1 scope was frozen on 2026-11-01: anything not listed in §4 is out of scope for v1.

| Amended | Change |
|---|---|
| 2026-11-02 | v1 provider changed from Anthropic to OpenRouter (free models) (§4, §8, §10). |
| 2026-11-13 | Added §14 Decisions (thread roots, empty threads, where merge blocks and anchor notes go, empty merges); §6 and §7 aligned. |
| 2026-11-15 | Added §14.5 branch state machine and §14.6 `merge_branch` checks; restore, archive and multiple merges added to the v2 backlog (§10). |
| 2026-11-16 | Added §14.7–§14.10 (what `check_invariants` and `pending_branches` cover, context building details). `api/` and `web/` implemented against [API.md](API.md). |
| 2026-11-17 | Editorial pass: neutral tone; §9 Ownership written as prose; §4, §8 and §12 aligned with the implementation. |
| 2026-11-17 | Conversation map added to the v1 scope (§4); the timeline view stays in the backlog. |
| 2026-11-17 | A branch starts from main as it was when it was opened: it sees the take-aways merged before that moment, even after its anchor (§7, §14.11; `branch.base_message_id` in §6). Images on user messages added to the v1 scope (§4, §6, §14.12). |
| 2026-11-17 | Documents on user messages (PDF, Word, plain text and code), read to text locally (§4, §6, §14.13). |
| 2026-11-17 | Take-away points written by hand in the merge checklist (§5, §6, §14.14). |
| 2026-11-17 | Conversation map redrawn as a tree of blocks with pan and zoom, always visible as a preview in the sidebar, full screen with a logbook (§4). A new branch takes the keyboard focus. |

## 1. Problem

LLM chat interfaces are linear. When an answer contains several points (1, 2, 3, 4…) and the user wants to follow up on two of them separately, there is no way to do it: every follow-up lands at the bottom of the conversation. The original answer drifts further away, the sub-discussions get mixed, and every tangent stays in the model's context forever.

## 2. Idea

1. Chat normally on a main thread.
2. Select one or more lines of any assistant answer → a side panel opens a branch anchored to that passage, where the user discusses it as if it were a new conversation.
3. Back on main, the user merges: for each branch the LLM produces a take-away made of short points, and the user picks which points go back into the main context.

## 3. Research question

When returning to the main thread after one or more branches, what should the model receive?

| Condition | What main sees of each branch |
|---|---|
| A. Linear baseline | The branch exchanges, appended to main in chronological order (= what a normal chat does today) |
| B. Full | Full branch messages, inserted at the merge point |
| C. Take-away | Only the auto-generated take-away points |
| D. Excluded | Nothing |

Measured: input tokens, quality of the next main answer, contamination (branch content leaking where it should not). Starting point: ContextBranch (arXiv 2512.13914), which compares branched vs linear but does not test a summarised merge. To verify before running: that this condition is not already covered.

## 4. v1 scope

In:

- BYOK: user pastes own API key (one provider in v1, OpenRouter, free models). Monthly spend cap, checked before every model call.
- Normal chat on main (no streaming).
- Select text in an assistant message → open branch in side panel.
- Branch chat.
- Images on user messages (PNG, JPEG, GIF, WebP; up to 4 per message), sent to models that accept them (§14.12).
- Documents on user messages (PDF with a text layer, Word .docx, plain text and source code), sent to any model as their text (§14.13).
- Merge with per-branch take-away, per-point include/exclude.
- Return-to-main warning.
- Conversation map: the current conversation drawn as a tree, like a skill tree. Main is a vertical trunk with one block per prompt and a knot per merge; each branch leaves the trunk at its anchor in its own colour, with one block per prompt, and merged branches come back into the trunk at their merge knot. Blocks show only the essentials: the start of the prompt and, on the first block of a branch, the passage it is anchored to. "Where you are" (the open branch, or the end of main) glows.
  - Always visible at the bottom of the sidebar as the shape of the tree only: a dot per node in its branch's colour (or main's), the whole tree fitted in the box (dots and lines keep their size on screen however small the tree is drawn; a tree too long for the box is shown full width around where you are), following the conversation and the open branch. The preview can be folded away ("Map" ▸), remembered across reloads; "Open map" stays.
  - "Open map" (or a click on the preview) shows it full screen: drag to move, wheel or + and − to zoom (around the pointer); the zoom, Fit and Where I am float bottom right, over the tree. A click on a block opens its details (the whole prompt, the start of its answer, the branches leaving that answer, or for a merge the branches that came back there), and only from the details does one go to it ("Go to this prompt", "Open branch").
  - On the left of the full-screen map: the conversation's title, then the logbook. Folded, the column goes away and the tree gets the whole screen: only a small card stays top left with the title and a "Logbook: 1 merge, 6 points" button that brings it back (remembered folded or open). Unfolded: the first prompt, every merge in order with each merged branch as a box in its colour, closed until opened, holding the points that entered the context (each expandable to its text; unticked points apart), then the branches still open and the discarded ones. Summaries of old messages (docs/CONTEXT.md) will join it.
  - Ways out: "Back to chat" top left, × top right, "Close map" bottom left, Escape (which first closes the details, if open).
- In the chat, a merge node lists each merged branch folded: its passage and "N points brought back"; a click shows the points (each expandable to its text) and "Open this branch".
- Opening a branch puts the keyboard in its message box: one types right away.
- Interface: green-ink theme (light and dark, following the system), serif for the model's answers; the user's messages on the right; the main column widens and centres when no branch is open. Each branch has its own lane colour, used everywhere the branch appears. A new branch puts its composer right under the hint; confirmations use the app's own dialog. Opening a branch and merging play a short synthesised sound and a brief animation (the sound can be switched off in Settings).
- Logging of every LLM call (for the experiment).

Out (v2 backlog, §10):

- Branches of branches (depth = 1).
- Scanned PDFs (no OCR), spreadsheets, presentations, archives.
- More than one side panel open at a time.
- Streaming, multiple providers, a timeline view.
- Editing past messages.
- Merging anywhere other than the current end of main.

## 5. User flow

1. **Setup:** paste API key, set spend cap. Key stored locally only, never committed, never sent anywhere but the provider.
2. **Main chat:** like any LLM chat.
3. **Branch:** select one or more lines of an assistant message → "Open branch" → side panel. The selected passage is shown quoted at the top of the panel.
4. **Back to main:** closing the panel returns to main. If there are branches with no merge decision, a non-intrusive but visible banner appears: "You came back from N branches. Merge?". Ignoring it is allowed: the user can keep chatting and merge later.
5. **Merge** (any time, while on main): for each pending branch, the LLM generates a take-away. The merge panel shows, per branch, a checklist:
   - each row = one point: short title (e.g. "added X", "solved Y", "noted Z") + checkbox;
   - a ▾ chevron expands the row to show the text that will actually enter the context;
   - the text and the title are editable;
   - the user can add points of their own: something the take-away missed, a different wording, or any text they want in the main context (§14.14). Branches can be merged or discarded independently.
6. **Main continues;** the next model call includes the checked points (§7).

Rule: a branch that is never merged is excluded from main's context. No hidden state: what the model sees is always exactly the checked point texts.

## 6. Data model (SQLite)

```sql
conversation(id, title, created_at)

message(
  id, conversation_id,
  branch_id NULL,          -- NULL = main thread
  parent_id NULL,          -- previous message in the same thread; NULL for the first message of main or of a branch (§14)
  role,                    -- user | assistant | merge
  content,
  created_at
)

branch(
  id, conversation_id,
  anchor_message_id,       -- assistant message on main the branch starts from
  anchor_start, anchor_end,-- char offsets of the selection in that message
  anchor_quote,            -- the selected text, copied (survives re-rendering)
  status,                  -- open | merged | discarded
  merge_message_id NULL,   -- the 'merge' node on main where it was merged
  created_at,
  base_message_id NULL     -- last message of main when the branch was opened (§14.11);
                           -- NULL for branches stored before it existed (= the anchor)
)

attachment(                -- files of a user message (§14.12, §14.13); not part of core
  id, message_id,
  position,
  kind,                    -- image | document
  mime, name, size,
  data BLOB,               -- the original file
  text NULL,               -- documents: the extracted text, what the model receives
  created_at
)

takeaway_point(
  id, branch_id,
  position,
  title,                   -- short label shown in the checklist
  text_generated,          -- what the LLM wrote (never overwritten)
  text_final,              -- what enters the context (= generated unless edited)
  included BOOLEAN,        -- checkbox
  origin                   -- model | user (added by hand; text_generated = '')
)

llm_call_log(
  id, conversation_id, branch_id NULL,
  purpose,                 -- chat | takeaway | experiment
  condition NULL,          -- A | B | C | D (experiment only)
  model, input_tokens, output_tokens, cost_estimate,
  prompt_json, response_text, created_at
)
```

Why keep `text_generated` and `text_final` apart: the experiment must measure the system (auto take-away), not the user's ability to rewrite it. For the same reason a point added by hand is marked `origin = user`.

## 7. Context construction

### Main thread

Walk the main messages from the root to the current end. At every merge node, take the checked points of the branches merged there and prepend them, in explicit delimiters, to the next user message (§14). A merge with zero checked points injects nothing:

```text
[merged from branch on: «<anchor_quote>»]
- <text_final of point 1>
- <text_final of point 2>
```

The `anchor_quote` header keeps the "what was this about" link.

### Inside a branch

1. Main messages from the root up to and including the anchor message (with any earlier merge nodes, so previously merged take-aways do propagate).
2. The merge blocks of the merge nodes between the anchor and the branch's **base**, the last message of main when the branch was opened (§14.11). A take-away merged before the branch existed is known to it, even when the merge came after the anchor: open a branch, merge it, then open a second branch on the same answer, and the second one knows what the first brought back. Only the take-aways cross: the user and assistant messages of main after the anchor stay out.
3. An anchor note, prepended (in explicit delimiters) to the branch's first user message, not sent as a system message (§14): "The user is asking about this specific passage of your previous answer: «<anchor_quote>»". The blocks of step 2 come before it.
4. The branch's own messages.

Sibling branches that are still open, or that are merged after this branch was opened, are not visible to it (isolation). The branch panel says how many merged take-aways the branch knows, so the rule stays visible.

## 8. Take-away generation

- Triggered on merge, once per branch, cached in `takeaway_point`; never regenerated silently.
- Lightweight free model (e.g. Gemma 4 26B A4B via OpenRouter), JSON output `[{ "title": "...", "text": "..." }]`, titles ≤ 5 words, 1–6 points. The format is requested in the prompt; the answer is parsed tolerantly (code fences, surrounding prose) and requested once more if it cannot be read.
- Default: all points checked (fast path for a user who wants to move on). The risk is that unread points enter the context; this is accepted and documented as a limitation.

## 9. Ownership

The work is split into two areas.

**The author's area.** The author owns the core of the project: the tree data model and its invariants, the context builder (§7), the merge logic and the inclusion of take-away points, and the experiment runner and its evaluation (§11). These are the parts the research question depends on. The author designs them, is responsible for them and can explain every line of them. They live in `core/` and `experiments/`.

**Delegated to Claude Code.** Everything else was delegated to Claude Code, and to Claude Code alone: the user interface (its components, the branch side panel and the merge checklist), the provider API client and its retries, the SQLite wiring and migrations, and the README with its demo GIF. These parts serve the core and take no decision about it. They live in `web/` and `api/`.

Claude Code may also review the core code.

## 10. v2 backlog

- Sequential merge at the graft point: merge branch N right where branch N+1 starts, so later branches build on what earlier ones explained (e.g. "explain using what I already know": branch 3 knows what branch 2 explained). Since §14.11 this already holds when branch N is merged *before* branch N+1 is opened; what remains is the case of branches open at the same time, which deliberately breaks sibling isolation. Worth testing as an experimental condition E.
- OCR for scanned PDFs (today: send the pages as images), spreadsheets (.xlsx) and presentations (.pptx) read to text.
- Depth > 1.
- Multiple panels, a timeline view, streaming, more providers (Anthropic, Gemini, Ollama).
- Trash & restore for discarded branches (DISCARDED → OPEN).
- Archive merged branches: a UI visibility flag, separate from status; take-aways stay in context.
- Multiple merges per branch: needs a `merge_event` table (`id, branch_id, merge_message_id, up_to_message_id`), take-aways attached to merge events instead of branches, and incremental summaries covering only messages since the previous merge.

## 11. Experiment (after v1)

- **Scenarios:** 15–20, from real conversations with multi-point answers; each scripted as: main prompt → 2–3 anchored branches → a main follow-up that depends (or should not depend) on branch content.
- **Conditions:** A–D (§3), all with auto-generated, all-checked take-aways.
- **Order of operations:** since §14.11 a branch opened after a merge sees that merge's take-away, so each scenario script fixes when every branch is opened and merged.
- **Metrics:** input tokens; next-answer quality (LLM judge blind to the condition, plus a blind human rating on a subset); contamination.
- **Output:** results table + 4–6 page technical report (not a paper), with limits stated: small n, LLM-as-judge bias, single provider, author-made scenarios.

## 12. Stack

- **Backend:** Python + FastAPI + SQLite (same language as the experiment runner).
- **Frontend:** TypeScript with React and Vite. Text selection with offsets needs a real DOM; Streamlit is not suitable.
- **Repo layout:** `core/`, `api/`, `web/`, `experiments/`, `docs/`, `tests/`.

## 13. Milestones

Milestones 1–4 are complete; milestone 5 is next.


1. Core: data model + context builder + unit tests (no UI).
2. Minimal UI: main chat + branch panel.
3. Merge flow + take-away generation + banner.
4. BYOK + spend cap + logging. → v1
5. Experiment + report + README with 10-second GIF.

## 14. Decisions

**14.1** A branch's first message has `parent_id = None`. `parent_id` always means "previous message in the same thread"; the link to main lives only in `branch.anchor_message_id`. This lets `thread()` treat main and branches identically.

**14.2** An empty thread returns `[]`, not an error. A just-opened branch is a valid state; errors are reserved for corrupt data. An empty branch cannot be merged, only discarded.

**14.3** Merge blocks and anchor notes are prepended to the next user message, never sent as separate system messages (the Anthropic API takes the system prompt only as a separate top-level parameter; mid-conversation system messages behave inconsistently across providers). Blocks are wrapped in explicit delimiters.

**14.4** A merge with zero checked points injects nothing. For the model it is equivalent to exclusion; in the data the branch stays merged (needed for history and the experiment).

**14.5** Branch state machine (v1): `OPEN → MERGED` and `OPEN → DISCARDED`; both are final. No restore, no discard after merge, no second merge. An empty branch cannot be merged (14.2).

Rationale: discarding after a merge would either rewrite main's history (take-aways vanish after the model already relied on them) or be a pure UI concern (archiving), not a state. To resume a merged topic, open a new branch on the same passage: it sees main, including the earlier take-aways. Restore, archive and multiple merges are in the v2 backlog (§10).

**14.6** `merge_branch` takes the conversation's messages and enforces the merge rules inside core: `merge_branch(branch, merge_message, messages)`. The merge node must already be in `messages`. Checks: the branch is OPEN (14.5); the merge node has role `merge`, is on main and belongs to the same conversation; the branch thread is not empty (14.2); the merge node is the last message of main (merging anywhere else is out of scope, §4). Several branches may be merged at the same node, as long as nothing follows it on main. Take-away points are not checked here: a merge with zero checked points is valid (14.4).

Rationale: keeping these rules in core (not in `api/`) makes them unit-testable and keeps them with the other tree rules (§9); both checks reuse `thread()`.

**14.7** `check_invariants` does not check "`text_generated` is never overwritten". It sees one snapshot of the state, so it cannot know what a field contained before. The rule is enforced where a point is edited: an edit changes only `text_final` (future core function `edit_point`; until then the API's `PATCH /api/points/{id}` can only write `included` and `text_final`).

**14.8** `pending_branches` returns every OPEN branch, empty ones included. An empty branch is still a pending decision; the UI offers "discard" instead of "merge" for it. Excluding them would complicate the signature for a marginal case; auto-discarding empty branches on return to main is a UI matter for v2.

**14.9** Take-away points may exist on any branch, not only merged ones: they are generated while the user is deciding (the checklist is shown before the merge is confirmed), so they exist on OPEN branches and stay on branches discarded afterwards. This is harmless: main's context uses only the points of MERGED branches. `check_invariants` therefore requires only that a point's branch exists.

**14.10** Context building details (`core/context.py`). Every block the app adds to a user message (a merge block or the anchor note) is wrapped on its own between the delimiters `<context>` and `</context>`, followed by a blank line and then what the user typed. Blocks of several branches merged at the same node are ordered by branch id, so the same state always gives the same context (needed for a reproducible experiment). `render_merge_block` returns the empty string when no point is checked, which is how 14.4 is applied. Blocks that have no user message after them yet (main ends on a merge node; a branch has no message) become a final user message of their own instead of being dropped, so nothing the user chose to bring back is ever hidden from the model.

**14.11** A branch records its **base**: `branch.base_message_id`, the last message of main when it was opened (`open_branch(..., base_message_id=...)`). `build_branch_context` adds the merge blocks of the merge nodes between the anchor and the base, in front of the anchor note. Before this, a branch saw main only up to its anchor, so a second branch opened on the same answer after a merge ignored that merge, contradicting the rationale of 14.5 ("open a new branch on the same passage: it sees main, including the earlier take-aways").

- *Why only the take-aways, not the messages of main after the anchor.* The anchor is what the branch is about; the exchanges that followed it on main may be on other topics. A take-away is different: the user chose to bring it back, so it is part of what the conversation knows.
- *Why frozen at opening, not "every merge so far".* A branch's context must not change under it: its earlier answers were produced without a later merge, and a sibling open at the same time stays isolated (the backlog item "sequential merge", §10, is the deliberate exception).
- *Consequence for shared merge nodes.* Branches merged together share the merge node at the end of main (14.6). Once a branch has been opened from that node (it is its base), joining it would make the later merge visible to that branch. `core.tree.reusable_merge_node` therefore returns the node only when no branch has it as base; otherwise the API appends a new merge node, so main can hold two consecutive merge nodes. `check_invariants` checks that a base is on main, not before its anchor, and that a merged branch's merge node comes after its base.
- *Stored branches.* `base_message_id` is NULL for branches stored before it existed; NULL means "the anchor", which is the old behaviour, so their contexts do not change.

**14.12** Images on user messages. They are stored in an `attachment` table outside `core`: the model input that `core.context` builds stays text, and each `ContextMessage` carries `source_id`, the stored message it renders, so the API can attach that message's images. The same rule as for text applies: an image is sent wherever its message is part of a context (main, and branches whose anchor comes after it). Validation: PNG, JPEG, GIF or WebP recognised by their first bytes, at most 4 per message, 5 MB each. A message with images is refused (`validation`) when the chosen model is known, from OpenRouter's model list, not to accept images; images already in the history are then replaced by a short note in the text, so the call does not fail and the log shows what was left out. The call log stores images as `attachment:<id>` references, not their bytes. The take-away prompt names the images of the branch (`[image attached: <name>]`) but does not send them.

**14.13** Documents on user messages: PDF (read with `pypdf`, page by page, marked `[page N]`), Word `.docx` (paragraph text from `word/document.xml`, standard library only) and plain text or source code (by extension, decoded as UTF-8 or UTF-16 with a BOM). Each is read to text **on this computer when it is attached** (`api/documents.py`); the original file is kept to be downloaded again. The model receives the text after what the user typed, one block per document between `<document name="…">` and `</document>`, wherever the message is part of a context, exactly like an image (14.12). Limits: 10 MB per file, 200,000 characters of text, 6 files per message (images included).

Rationale: OpenRouter can parse PDFs itself, but then the model reads a text the app never sees, and some parsing engines are charged. Extracting locally keeps "no hidden state": the call log holds exactly the text the model read, it costs nothing, and it works with every model, including text-only ones. The price is that a scanned PDF has no text to read; it is refused with a message that suggests sending its pages as images. A document is only ever downloaded, never shown inline, so an `.html` file cannot run in the app's page.

**14.14** The user can add take-away points by hand, in the merge checklist, while the branch is open. Such a point has `origin = user` and `text_generated = ''` (nothing was generated); it is included by default and enters the context exactly like a generated one, through `text_final`, so `core.context` needs no change. Its title is the one the user gives or the first five words of its text. A point the user added can be deleted; a generated point can only be unticked (its text stays as the record of what the model wrote, 14.7). Regenerating replaces only the generated points: the user's stay, after the new ones. A branch whose points were all written by hand can be merged without generating a take-away.

Rationale: the checklist is the only door from a branch to main. If the model misses something, or the user wants it in other words, or wants to put any text at all in front of the next message (a deliberate injection of context), that text should go through the same visible, delimited block rather than be typed into the next message by hand. `origin` keeps the experiment honest: condition C (§3) is measured on generated points only.
