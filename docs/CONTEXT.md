# Context management: how long is too long, and summarising old messages

**Status:** design, 2026-11-17. Nothing here is implemented yet. The rules in §3 change what
the model receives, so they belong to `core/` and to the author (DESIGN §9); this document
proposes them for review.

Two problems, one principle:

1. **Knowing when a chat is too long**, for the model actually in use: a 32k model and a
   1M model have very different limits, and quality drops well before the hard limit.
2. **Shrinking it on purpose**: select the old part of main and replace it, in the model's
   input, with a **deep summary**: longer, more structured and slower to produce than a
   branch take-away.

The principle is the one of merges (DESIGN §5): **no hidden state**. Nothing is summarised
without the user seeing the list of points first; every point can be unticked, edited or
added by hand; the original messages are never deleted; the log shows exactly what was sent.

## 1. Measuring length per model

### What we already know exactly

- **The size of the last context of each thread.** Every call stores `input_tokens` and
  `output_tokens` in `llm_call_log`, as counted by the provider with the model's own
  tokenizer (images included). After a reply, the next context of that thread is at least
  `input + output` of the last call, plus the next user message.
- **The window of the model.** OpenRouter's `/api/v1/models` gives `context_length` and
  `top_provider.max_completion_tokens` for every model. Today the app reads only the free
  ones; the meter needs the whole list (cached like now), because a model typed by hand can
  be a paid one.

### What has to be estimated

- **Text not sent yet** (the message being typed, a document about to be attached, a branch
  never used). Estimate with characters ÷ a ratio, and **calibrate the ratio per
  conversation and model** from the logged calls: `ratio = input_tokens / characters sent`.
  The first message of a conversation uses 4 characters per token.
- **A branch's context before its first call**: main up to its base (DESIGN §14.11) plus the
  anchor note, estimated the same way.

### Thresholds

The usable part of the window is `context_length − reserve`, where `reserve` is the room for
the answer (`max_completion_tokens`, or 4,096 when unknown). On that, three levels:

| level | default | what the UI does |
|---|---|---|
| fine | below 50% | a thin bar under the composer, nothing else |
| long | 50–80% | the bar turns amber; a line says "This chat is getting long for *model*" with "Summarise old messages…" |
| too long | above 80% | red; the same offer becomes a banner above the composer; sending still works |
| over | above 100% | the message is refused before the call (`context_too_long`), with the offer to summarise or switch model |

Why 50% and not 90%: models answer worse long before the window is full (facts in the middle
of a long context are used less). The two percentages are a setting, per model if the user
wants: a model known to hold up well can be set to warn later.

Shown everywhere a context exists: under the composer of main and of each branch, with the
tokens (`18.4k of 128k`) on hover. For paid models the hover also shows the estimated cost of
the next message (`tokens × prompt price` from the same model list).

Free-tier note: OpenRouter's free limit counts **requests**, not tokens (DISTRIBUTION §1),
so length does not cost free users quota; it costs answer quality.

## 2. The user flow for a summary

1. **Choose the span.** "Summarise old messages…" opens the conversation map (or the thread)
   in a selection mode. The span always **starts at the beginning of main** (or right after
   the previous summary, see §3) and the user picks where it ends: an answer of the model.
   The meter shows live how much the context would shrink (estimated from the length of the
   span against the expected summary, about 10–15% of it).
2. **Generate.** The model writes the summary. It can take longer than a take-away (tens of
   seconds, or minutes for long spans): it runs in the background with a progress line, and
   the user can keep reading meanwhile. A separate "summary model" setting allows a stronger
   model than the chat one.
3. **Review the checklist.** Exactly like the merge checklist, and with its new features
   (DESIGN §14.14):
   - points grouped by kind: **decisions**, **facts and figures**, **the user's preferences
     and constraints**, **artefacts** (code, names, numbers that must survive verbatim),
     **open questions**;
   - each point ticked by default, with a title and a text; ▾ shows and edits the text;
   - **add a point** by hand in any group: what the model missed, a wording of one's own,
     or any text one wants the model to keep;
   - regenerate (keeps the points written by hand), or cancel: nothing changes until Apply.
   - before Apply: "the context goes from 61k to 9k tokens (estimated)".
4. **Apply.** From the next call on, the model receives the summary instead of the messages
   of the span. In the chat those messages stay where they are, folded under a line
   "Summarised: 34 messages → 18 points (show)", still readable, still selectable for a
   branch.
5. **Undo.** The most recent summary can be removed: the messages come back into the
   context. Nothing was deleted, so this is safe; the log keeps what was sent while the
   summary was in place.

## 3. Rules for the context builder (proposal for `core/`)

### Data

```sql
summary(
  id, conversation_id,
  from_message_id,        -- first message of main covered (the root, or right after the previous summary)
  to_message_id,          -- last message covered: an assistant message or a merge node
  status,                 -- draft | applied | removed
  model, created_at, applied_at NULL
)

summary_point(
  id, summary_id, position,
  section,                -- decisions | facts | preferences | artefacts | open_questions
  title, text_generated, text_final, included, origin   -- as takeaway_point (§14.14)
)
```

A draft affects nothing. Only `applied` summaries enter a context.

### Main

Applied summaries **tile the beginning of main**: the first covers `root..k1`, the next
`k1+1..k2`, and so on, contiguous and non-overlapping. Tiling only from the start keeps the
order of the conversation: an old part is replaced, the recent part stays verbatim.

`build_main_context` walks main as today; when it meets the first message of an applied
summary it skips to the message after `to_message_id` and adds the summary's block to
`pending`, so it lands in front of the next user message, in `<context>` delimiters, like a
merge block:

```text
<context>
[summary of the conversation so far: 34 messages]
Decisions:
- Images are served as AVIF with a WebP fallback.
Facts and figures:
- The page weighs 2.1 MB; the target is under 500 KB.
Open questions:
- Whether to lazy-load the gallery.
</context>
```

Merge nodes inside a span: their take-aways are part of what the summariser reads (it gets
the span as main's context renders it), so they are summarised too, not repeated.

### Branches

- A branch opened **before** a summary was applied keeps the context it had: like merges
  after its base (§14.11), a summary applied later is not visible to it.
- A branch opened **after**, whose anchor comes **after** the summarised span, sees the
  summary in place of the span, like main.
- A branch whose anchor is **inside** a summarised span sees main **verbatim** up to its anchor:
  it is about that old passage and needs the real text around it. (Its base still brings in
  later merges as usual.)

### Invariants to add to `check_invariants`

- applied summaries of a conversation are contiguous from the root and do not overlap;
- `to_message_id` is on main, after `from_message_id`, and is an assistant message or a
  merge node;
- only the last applied summary can be removed (otherwise the tiling breaks);
- summary points: positions unique per summary, sections from the fixed list.

## 4. The summariser

- **Prompt**: "Summarise this part of a conversation so that the conversation can continue
  without it." It asks for JSON grouped by the five sections, 5–40 points, self-contained
  sentences, and **verbatim** reproduction of code, numbers, names and anything the user
  marked as important. Written in the conversation's language. Like the take-away prompt,
  its wording is the owner's to decide.
- **Long spans** that do not fit the summary model's own window: summarise in chunks of
  whole exchanges, then merge the partial summaries in a last call (map-reduce). The
  checklist shows the final points only.
- **Images and documents** in the span: the summariser receives the text of documents and
  the images (if the model accepts them); artefacts from them go to "artefacts".
- **Cost and quota**: one call per chunk plus one; the UI says how many calls before
  starting, because on the free tier each counts against the 50 a day.
- **Logged** with a new purpose `summary` in `llm_call_log`.

## 5. Plan

1. **Meter, read-only.** Full model list with context lengths; per-thread tokens from the log
   plus the calibrated estimate; the bar under every composer; the `context_too_long` refusal.
   No change to `core/`.
2. **Summaries in `core/`** (author): data model, the rules of §3 in `build_main_context` and
   `build_branch_context`, invariants, tests. Nothing in the UI yet.
3. **Summariser and checklist** in `api/` and `web/`, reusing the merge checklist (points,
   editing, points by hand).
4. **Suggestions.** When a thread crosses "long", propose a span: the oldest exchanges whose
   removal brings the context back under 40%, ending on an answer.

## 6. Open questions

1. Should the summary replace the span **for branches anchored inside it** too, with the
   anchor message itself kept verbatim? Cheaper, but the branch loses the text around its
   passage.
2. Is "tile from the start" too strict? Summarising a middle span (keeping the first
   messages, which often hold the task statement) would need the block to sit in the middle of
   main, which the current "prepend to the next user message" rule supports, but makes undo and
   overlaps harder.
3. For the experiment: is a summarised main a new condition, or a confound to keep out of the
   scenarios?
4. Should a branch be summarisable the same way, when it grows long before being merged?
