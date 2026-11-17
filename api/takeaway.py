"""Take-away generation (DESIGN.md §8): the prompt and the parsing of the model's answer.

Pure functions, no I/O. ``api.service`` makes the call, stores the points and
logs it.

NOTE FOR THE OWNER: the wording of ``SYSTEM_PROMPT`` and ``build_prompt`` decides
what condition C of the experiment (§3) measures. It lives here because the
generation plumbing was delegated, but the text is yours to review and change.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from api.provider import ChatMessage
from core.models import Message, Role

MIN_POINTS = 1
MAX_POINTS = 6
MAX_TITLE_WORDS = 5

SYSTEM_PROMPT = (
    "You write take-aways for a branching chat application. A user left the main "
    "conversation to discuss one passage of an assistant answer in a side conversation. "
    "You extract what is worth carrying back to the main conversation, as a few short points. "
    "You answer with JSON only."
)

INSTRUCTIONS = f"""\
Return ONLY a JSON array of {MIN_POINTS} to {MAX_POINTS} objects, each {{"title": "...", "text": "..."}}:
- "title": a label of at most {MAX_TITLE_WORDS} words (for example "added X", "solved Y", "noted Z");
- "text": one or two self-contained sentences stating the point, understandable without reading the side conversation;
- write in the language of the side conversation;
- include only what the side conversation actually established: no filler, no commentary about the conversation itself.
No text before or after the JSON array."""

RETRY_NUDGE = (
    "Your previous answer could not be read as the requested JSON. "
    'Answer again with ONLY the JSON array of {"title": "...", "text": "..."} objects.'
)


@dataclass(frozen=True)
class GeneratedPoint:
    title: str
    text: str


class TakeawayParseError(ValueError):
    """The model's answer does not contain a usable list of points."""


def build_prompt(
    anchor_quote: str,
    branch_messages: Sequence[Message],
    files: Mapping[int, Sequence[tuple[str, str]]] | None = None,
) -> list[ChatMessage]:
    """The messages sent to the model to summarise one branch.

    ``branch_messages`` is the branch thread in order (``core.tree.thread``).
    ``files`` maps a message id to the ``(kind, name)`` of the files attached to
    it (kind: image | document): the transcript names them, it does not include
    them, since the assistant's answers already say what mattered in them.
    """
    lines = []
    for message in branch_messages:
        speaker = "User" if message.role == Role.USER else "Assistant"
        text = message.content
        for kind, name in (files or {}).get(message.id, []):
            note = f"[{kind} attached: {name}]"
            text = f"{text}\n{note}" if text else note
        lines.append(f"[{speaker}]\n{text}")
    transcript = "\n\n".join(lines)
    user = (
        "Passage the side conversation is about:\n"
        f"«{anchor_quote}»\n\n"
        "Side conversation:\n"
        f"{transcript}\n\n"
        f"{INSTRUCTIONS}"
    )
    return [ChatMessage("system", SYSTEM_PROMPT), ChatMessage("user", user)]


def retry_prompt(prompt: Sequence[ChatMessage], bad_answer: str) -> list[ChatMessage]:
    """The prompt for the second attempt, after an unreadable answer."""
    return [*prompt, ChatMessage("assistant", bad_answer), ChatMessage("user", RETRY_NUDGE)]


_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*$", re.DOTALL)


def _load_json(text: str) -> object:
    """Find the JSON value in an answer that may wrap it in a code fence or in prose."""
    text = text.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Prose around the array: take the outermost [...] and try again.
    start, end = text.find("["), text.rfind("]")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise TakeawayParseError("the answer is not JSON")


def _clean_title(title: str) -> str:
    words = title.split()
    return " ".join(words[:MAX_TITLE_WORDS])


def title_from(text: str) -> str:
    """A checklist title of at most five words, for a point the user writes or renames."""
    return _clean_title(text)


def parse(answer: str) -> list[GeneratedPoint]:
    """Turn the model's answer into 1–6 points.

    Tolerant about packaging (code fences, surrounding prose, an object wrapping
    the array), strict about content: every kept point has a non-blank title
    and text. Extra points beyond the sixth are dropped; titles are cut to five
    words. The point texts are kept exactly as written, apart from outer
    whitespace.

    Raises:
        TakeawayParseError: if no valid point can be read.
    """
    data = _load_json(answer)
    if isinstance(data, dict):
        lists = [value for value in data.values() if isinstance(value, list)]
        if len(lists) != 1:
            raise TakeawayParseError("the answer is a JSON object, not an array of points")
        data = lists[0]
    if not isinstance(data, list):
        raise TakeawayParseError("the answer is not a JSON array")

    points = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title, text = item.get("title"), item.get("text")
        if not isinstance(title, str) or not isinstance(text, str):
            continue
        title, text = _clean_title(title), text.strip()
        if title and text:
            points.append(GeneratedPoint(title=title, text=text))
    if len(points) < MIN_POINTS:
        raise TakeawayParseError("the answer contains no valid point")
    return points[:MAX_POINTS]
