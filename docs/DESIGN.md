DESIGN.md — GraftChat

Anchored branching chat for LLMs: graft side conversations onto any passage of an answer, then bring back only what matters.

Status: v1 design, frozen on 2026-11-01. Anything not listed in v1 scope is out of scope until v1 ships.
Amended 2026-11-02: v1 provider changed from Anthropic to OpenRouter (free models) (§4, §8, §10).

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
  parent_id NULL,          -- previous message in the same thread
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

Walk the main messages from the root to the current end. At every merge node, insert the checked points of the branches merged there:

[merged from branch on: «<anchor_quote>»]
- <text_final of point 1>
- <text_final of point 2>

The anchor_quote header keeps the "what was this about" link.

Inside a branch
Main messages from the root up to and including the anchor message (with any earlier merge nodes, so previously merged take-aways do propagate).
A system note: "The user is asking about this specific passage of your previous answer: «<anchor_quote>»".
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