DESIGN.md — GraftChat

Anchored branching chat for LLMs: graft side conversations onto any passage of an answer, then bring back only what matters.

Status: v1 design, frozen on 2026-11-01. Anything not listed in v1 scope is out of scope until v1 ships.
Amended 2026-11-02: v1 provider changed from Anthropic to OpenRouter (free models) (§4, §8, §10).
Amended 2026-11-13: added §14 Decisions (thread roots, empty threads, where merge blocks and anchor notes go, empty merges); §6 and §7 aligned.
Amended 2026-11-15: added §14.5 branch state machine and §14.6 merge_branch checks; restore, archive and multiple merges added to the v2 backlog (§10).
Amended 2026-11-16: added §14.7–§14.10 (what check_invariants and pending_branches cover, context building details). api/ and web/ implemented against docs/API.md.

1. Problem

LLM chat interfaces are linear. When an answer contains several points (1, 2, 3, 4…) and I want to follow up on two of them separately, I can't: every follow-up lands at the bottom of the conversation. The original answer drifts further away, the sub-discussions get mixed, and every tangent stays in the model's context forever.

2. Idea
Chat normally on a main thread.
Select one or more lines of any assistant answer → a side panel opens a branch anchored to that passage, where I chat about it as if it were a new conversation.
Back on main, I merge: for each branch the LLM produces a take-away made of short points. I pick which points go back into the main context.
3. Research question

When returning to the main thread after one or more branches, what should the model receive?

Condition	What main sees of each branch
A. Linear baseline	The branch exchanges, appended to main in chronological order (= what a normal chat does today)
B. Full	Full branch messages, inserted at the merge point
C. Take-away	Only the auto-generated take-away points
D. Excluded	Nothing

Measured: input tokens, quality of the next main answer, contamination (branch content leaking where it shouldn't). Starting point: ContextBranch (arXiv 2512.13914), which compares branched vs linear but does not test a summarised merge. To verify before running: that this condition is not already covered.

4. v1 scope

In:

BYOK: user pastes own API key (one provider in v1, OpenRouter, free models). Hard monthly spend cap enforced client-side.
Normal chat on main (no streaming).
Select text in an assistant message → open branch in side panel.
Branch chat.
Merge with per-branch take-away, per-point include/exclude.
Return-to-main warning.
Logging of every LLM call (for the experiment).

Out (v2 backlog, §10):

Branches of branches (depth = 1).
More than one side panel open at a time.
Streaming, multiple providers, timeline/graph view.
Editing past messages.
Merging anywhere other than the current end of main.
5. User flow
Setup: paste API key, set spend cap. Key stored locally only, never committed, never sent anywhere but the provider.
Main chat: like any LLM chat.
Branch: select one or more lines of an assistant message → "Open branch" → side panel. The selected passage is shown quoted at the top of the panel.
Back to main: closing the panel returns to main. If there are branches with no merge decision, a non-intrusive but visible banner appears: "You came back from N branches. Merge?". Ignoring it is allowed: the user can keep chatting and merge later.
Merge (any time, while on main): for each pending branch, the LLM generates a take-away. The merge panel shows, per branch, a Notion-style checklist:
each row = one point: short title (e.g. "added X", "solved Y", "noted Z") + checkbox;
a ▾ chevron expands the row to show the text that will actually enter the context;
the text is editable. Branches can be merged or discarded independently.
Main continues; the next model call includes the checked points (§7).

Rule: a branch that is never merged is excluded from main's context. No hidden state: what the model sees is always exactly the checked point texts.

6. Data model (SQLite)
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
  created_at
)

takeaway_point(
  id, branch_id,
  position,
  title,                   -- short label shown in the checklist
  text_generated,          -- what the LLM wrote (never overwritten)
  text_final,              -- what enters the context (= generated unless edited)
  included BOOLEAN         -- checkbox
)

llm_call_log(
  id, conversation_id, branch_id NULL,
  purpose,                 -- chat | takeaway | experiment
  condition NULL,          -- A | B | C | D (experiment only)
  model, input_tokens, output_tokens, cost_estimate,
  prompt_json, response_text, created_at
)

Why keep text_generated and text_final apart: the experiment must measure the system (auto take-away), not the user's ability to rewrite it.

7. Context construction
Main thread

Walk the main messages from the root to the current end. At every merge node, take the checked points of the branches merged there and prepend them, in explicit delimiters, to the next user message (§14). A merge with zero checked points injects nothing:

[merged from branch on: «<anchor_quote>»]
- <text_final of point 1>
- <text_final of point 2>

The anchor_quote header keeps the "what was this about" link.

Inside a branch
Main messages from the root up to and including the anchor message (with any earlier merge nodes, so previously merged take-aways do propagate).
An anchor note, prepended (in explicit delimiters) to the branch's first user message, not sent as a system message (§14): "The user is asking about this specific passage of your previous answer: «<anchor_quote>»".
The branch's own messages.

Sibling branches are not visible to each other (isolation).

8. Take-away generation
Triggered on merge, once per branch, cached in takeaway_point; never regenerated silently.
Lightweight free model (e.g. Gemma 4 26B A4B via OpenRouter), structured JSON output: [{ "title": "...", "text": "..." }], titles ≤ 5 words, 1–6 points.
Default: all points checked (fast path: the user is in a hurry). The risk is that unread points enter the context; this is accepted and documented as a limitation.
9. Ownership
Written by Francesco (core, must be defensible in an interview)	Delegated to Claude Code
Tree/data model and its invariants	UI components, side panel, merge checklist
Context builder (§7)	Provider API client, retries
Merge logic and point inclusion	SQLite wiring/migrations
Experiment runner and evaluation (§11)	README polish, GIF

Claude Code may review core code, not write it.

10. v2 backlog
Sequential merge at the graft point (Francesco's idea): merge branch N right where branch N+1 starts, so later branches build on what earlier ones explained (e.g. "explain using what I already know": branch 3 knows I learned branch 2's content). Note: this deliberately breaks sibling isolation. Worth testing as an experimental condition E.
Depth > 1.
Multiple panels, timeline/graph view, streaming, more providers (Anthropic, Gemini, Ollama).
Trash & restore for discarded branches (DISCARDED → OPEN).
Archive merged branches: a UI visibility flag, separate from status; take-aways stay in context.
Multiple merges per branch: needs a merge_event table (id, branch_id, merge_message_id, up_to_message_id), take-aways attached to merge events instead of branches, and incremental summaries covering only messages since the previous merge.
11. Experiment (after v1)
Scenarios: 15–20, from real conversations with multi-point answers; each scripted as: main prompt → 2–3 anchored branches → a main follow-up that depends (or should not depend) on branch content.
Conditions: A–D (§3), all with auto-generated, all-checked take-aways.
Metrics: input tokens; next-answer quality (LLM judge blind to the condition, plus Francesco's blind rating on a subset); contamination.
Output: results table + 4–6 page technical report (not a paper), with limits stated: small n, LLM-as-judge bias, single provider, author-made scenarios.
12. Stack (proposed)
Backend: Python + FastAPI + SQLite (same language as the experiment runner).
Frontend: plain TypeScript (React/Vite). Text selection with offsets needs a real DOM; Streamlit is not suitable.
Repo layout: core/ (Francesco), api/, web/, experiments/, docs/.
13. Milestones
Core: data model + context builder + unit tests (no UI).
Minimal UI: main chat + branch panel.
Merge flow + take-away generation + banner.
BYOK + spend cap + logging. → v1
Experiment + report + README with 10-second GIF.
14. Decisions
14.1 A branch's first message has parent_id = None. parent_id always means "previous message in the same thread"; the link to main lives only in branch.anchor_message_id. This lets thread() treat main and branches identically.
14.2 An empty thread returns [], not an error. A just-opened branch is a valid state; errors are reserved for corrupt data. An empty branch cannot be merged, only discarded.
14.3 Merge blocks and anchor notes are prepended to the next user message, never sent as separate system messages (the Anthropic API takes the system prompt only as a separate top-level parameter; mid-conversation system messages behave inconsistently across providers). Blocks are wrapped in explicit delimiters.
14.4 A merge with zero checked points injects nothing. For the model it is equivalent to exclusion; in the data the branch stays merged (needed for history and the experiment).
14.5 Branch state machine (v1): OPEN → MERGED and OPEN → DISCARDED; both are final. No restore, no discard after merge, no second merge. An empty branch cannot be merged (14.2).
Rationale: discarding after a merge would either rewrite main's history (take-aways vanish after the model already relied on them) or be a pure UI concern (archiving), not a state. To resume a merged topic, open a new branch on the same passage: it sees main, including the earlier take-aways. Restore, archive and multiple merges are in the v2 backlog (§10).
14.6 merge_branch takes the conversation's messages and enforces the merge rules inside core: merge_branch(branch, merge_message, messages). The merge node must already be in messages. Checks: the branch is OPEN (14.5); the merge node has role merge, is on main and belongs to the same conversation; the branch thread is not empty (14.2); the merge node is the last message of main (merging anywhere else is out of scope, §4). Several branches may be merged at the same node, as long as nothing follows it on main. Take-away points are not checked here: a merge with zero checked points is valid (14.4).
Rationale: keeping these rules in core (not in api/) makes them unit-testable and part of the defensible core (§9); both checks reuse thread().
14.7 check_invariants does not check "text_generated is never overwritten". It sees one snapshot of the state, so it cannot know what a field contained before. The rule is enforced where a point is edited: an edit changes only text_final (future core function edit_point; until then the API's PATCH /api/points/{id} can only write included and text_final).
14.8 pending_branches returns every OPEN branch, empty ones included. An empty branch is still a pending decision; the UI offers "discard" instead of "merge" for it. Excluding them would complicate the signature for a marginal case; auto-discarding empty branches on return to main is a UI matter for v2.
14.9 Take-away points may exist on any branch, not only merged ones: they are generated while the user is deciding (the checklist is shown before the merge is confirmed), so they exist on OPEN branches and stay on branches discarded afterwards. This is harmless: main's context uses only the points of MERGED branches. check_invariants therefore requires only that a point's branch exists.
14.10 Context building details (core/context.py). Every block the app adds to a user message (a merge block or the anchor note) is wrapped on its own between the delimiters <context> and </context>, followed by a blank line and then what the user typed. Blocks of several branches merged at the same node are ordered by branch id, so the same state always gives the same context (needed for a reproducible experiment). render_merge_block returns the empty string when no point is checked, which is how 14.4 is applied. Blocks that have no user message after them yet (main ends on a merge node; a branch has no message) become a final user message of their own instead of being dropped, so nothing the user chose to bring back is ever hidden from the model.
