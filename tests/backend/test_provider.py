"""Tests for ``api.provider``: OpenRouter parsing, retries, error mapping, model list."""

from __future__ import annotations

import json

import httpx
import pytest

from api.provider import (
    ChatMessage,
    FakeProvider,
    OpenRouterProvider,
    ProviderError,
    fetch_free_models,
)

MESSAGES = [ChatMessage("user", "hello")]


def ok(text="hi there", **usage):
    usage = usage or {"prompt_tokens": 11, "completion_tokens": 7, "cost": 0.0015}
    return httpx.Response(
        200,
        json={
            "model": "vendor/model:free",
            "choices": [{"message": {"content": text}}],
            "usage": usage,
        },
    )


def provider(responses, sleeps=None, **kwargs):
    """A provider whose transport answers with the queued responses (or raises them)."""
    queue = list(responses)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    sleeps = sleeps if sleeps is not None else []
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterProvider("sk-test", client=client, sleep=sleeps.append, **kwargs), seen


def test_success_parses_text_usage_and_cost():
    p, seen = provider([ok()])
    result = p.complete("vendor/model:free", MESSAGES)

    assert (result.text, result.model) == ("hi there", "vendor/model:free")
    assert (result.input_tokens, result.output_tokens, result.cost) == (11, 7, 0.0015)
    request = seen[0]
    assert request.url == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {
        "model": "vendor/model:free",
        "messages": [{"role": "user", "content": "hello"}],
    }


def test_missing_usage_means_zero():
    p, _ = provider([httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})])
    result = p.complete("m", MESSAGES)
    assert (result.input_tokens, result.output_tokens, result.cost, result.model) == (0, 0, 0.0, "m")


def test_retries_rate_limit_then_succeeds_and_honours_retry_after():
    sleeps = []
    limited = httpx.Response(
        429, json={"error": {"message": "slow down"}}, headers={"retry-after": "3"}
    )
    p, seen = provider([limited, httpx.Response(503, json={}), ok()], sleeps)

    assert p.complete("m", MESSAGES).text == "hi there"
    assert len(seen) == 3
    assert len(sleeps) == 2 and sleeps[0] >= 3


def test_gives_up_after_max_attempts_with_the_last_error():
    limited = httpx.Response(429, json={"error": {"message": "slow down"}})
    p, seen = provider([limited] * 3, max_attempts=3)
    with pytest.raises(ProviderError) as info:
        p.complete("m", MESSAGES)
    assert info.value.kind == "rate_limit"
    assert "slow down" in info.value.message
    assert len(seen) == 3


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (403, "auth"), (402, "error"), (400, "error"), (404, "error")],
)
def test_permanent_errors_are_not_retried(status, kind):
    p, seen = provider([httpx.Response(status, json={"error": {"message": "nope"}})])
    with pytest.raises(ProviderError) as info:
        p.complete("m", MESSAGES)
    assert info.value.kind == kind
    assert "nope" in info.value.message
    assert len(seen) == 1


def test_network_errors_and_timeouts_are_retried():
    p, seen = provider([httpx.ConnectError("down"), httpx.ReadTimeout("slow"), ok()])
    assert p.complete("m", MESSAGES).text == "hi there"
    assert len(seen) == 3


def test_error_inside_a_200_body_is_an_error():
    body = {"error": {"code": 401, "message": "bad key"}}
    p, seen = provider([httpx.Response(200, json=body)])
    with pytest.raises(ProviderError) as info:
        p.complete("m", MESSAGES)
    assert info.value.kind == "auth"
    assert len(seen) == 1


def test_empty_answer_is_retried_then_fails():
    p, seen = provider([ok(text="  ")] * 2, max_attempts=2)
    with pytest.raises(ProviderError, match="empty answer"):
        p.complete("m", MESSAGES)
    assert len(seen) == 2


def test_non_json_error_body_still_gives_a_message():
    p, _ = provider([httpx.Response(400, text="<html>bad</html>")])
    with pytest.raises(ProviderError, match="HTTP 400"):
        p.complete("m", MESSAGES)


def test_free_models_are_filtered_and_sorted():
    free = {"prompt": "0", "completion": "0"}
    data = [
        {"id": "z/paid", "name": "Paid", "pricing": {"prompt": "0.000001", "completion": "0"}},
        {"id": "b/free", "name": "beta", "context_length": 8000, "pricing": free},
        {"id": "a/free", "name": "Alpha", "pricing": free},
        {
            "id": "img/free",
            "name": "Image",
            "pricing": free,
            "architecture": {"output_modalities": ["image"]},
        },
        {
            "id": "music/free",
            "name": "Music",
            "pricing": free,
            "architecture": {"output_modalities": ["text", "audio"]},
        },
        {"id": "x/nopricing", "name": "X"},
        "garbage",
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": data}))
    models = fetch_free_models(httpx.Client(transport=transport))
    assert [(m.id, m.context_length) for m in models] == [("a/free", None), ("b/free", 8000)]


def test_model_list_failure_is_a_provider_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    with pytest.raises(ProviderError):
        fetch_free_models(httpx.Client(transport=transport))


def test_fake_provider_answers_chat_and_takeaway():
    fake = FakeProvider()
    chat = fake.complete("any", MESSAGES)
    assert "hello" in chat.text and chat.cost == 0.0
    points = json.loads(fake.complete("any", MESSAGES, tag="takeaway").text)
    assert 1 <= len(points) <= 6 and all({"title", "text"} <= set(p) for p in points)
