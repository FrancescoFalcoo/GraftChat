"""Tests for ``api.takeaway``: prompt building and tolerant parsing."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from api.takeaway import (
    GeneratedPoint,
    TakeawayParseError,
    build_prompt,
    parse,
    retry_prompt,
)
from core.models import Message, Role

T = datetime(2026, 1, 1)
POINTS = [{"title": "added X", "text": "X was added."}, {"title": "solved Y", "text": "Y is solved."}]
EXPECTED = [GeneratedPoint("added X", "X was added."), GeneratedPoint("solved Y", "Y is solved.")]


def test_prompt_contains_quote_and_transcript_in_order():
    thread = [
        Message(10, 1, 5, None, Role.USER, "why is it so?", T),
        Message(11, 1, 5, 10, Role.ASSISTANT, "because of Z", T),
    ]
    system, user = build_prompt("the passage", thread)

    assert (system.role, user.role) == ("system", "user")
    assert "«the passage»" in user.content
    assert user.content.index("[User]\nwhy is it so?") < user.content.index("[Assistant]\nbecause of Z")
    assert "JSON array" in user.content


def test_retry_prompt_shows_the_bad_answer():
    prompt = build_prompt("q", [Message(10, 1, 5, None, Role.USER, "hi", T)])
    again = retry_prompt(prompt, "Sure! Here you go")
    assert again[:2] == prompt
    assert [m.role for m in again[2:]] == ["assistant", "user"]
    assert again[2].content == "Sure! Here you go"


@pytest.mark.parametrize(
    "answer",
    [
        json.dumps(POINTS),
        "  \n" + json.dumps(POINTS, indent=2) + "\n",
        "```json\n" + json.dumps(POINTS) + "\n```",
        "```\n" + json.dumps(POINTS) + "\n```",
        "Here are the points:\n" + json.dumps(POINTS) + "\nHope this helps!",
        json.dumps({"points": POINTS}),
    ],
    ids=["plain", "whitespace", "json-fence", "bare-fence", "prose-around", "wrapped-in-object"],
)
def test_parse_accepts_common_packagings(answer):
    assert parse(answer) == EXPECTED


def test_parse_keeps_text_verbatim_apart_from_outer_whitespace():
    answer = json.dumps([{"title": "  noted   Z ", "text": "  Line one.\n\nLine  two.  "}])
    assert parse(answer) == [GeneratedPoint("noted Z", "Line one.\n\nLine  two.")]


def test_parse_cuts_titles_to_five_words_and_points_to_six():
    items = [{"title": "one two three four five six seven", "text": f"t{i}"} for i in range(9)]
    points = parse(json.dumps(items))
    assert len(points) == 6
    assert points[0].title == "one two three four five"
    assert [p.text for p in points] == [f"t{i}" for i in range(6)]


def test_parse_skips_invalid_items_but_keeps_valid_ones():
    items = [
        "just a string",
        {"title": "no text"},
        {"title": "", "text": "blank title"},
        {"title": "blank text", "text": "   "},
        {"title": 3, "text": "number title"},
        {"title": "good", "text": "kept"},
    ]
    assert parse(json.dumps(items)) == [GeneratedPoint("good", "kept")]


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "I could not summarise this.",
        "[]",
        json.dumps([{"title": "", "text": ""}]),
        json.dumps({"a": [], "b": []}),
        json.dumps("a string"),
        "[{broken json",
    ],
    ids=["empty", "prose", "empty-array", "only-blank", "ambiguous-object", "json-string", "broken"],
)
def test_parse_rejects_unusable_answers(answer):
    with pytest.raises(TakeawayParseError):
        parse(answer)
