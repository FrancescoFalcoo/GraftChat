"""LLM provider client: OpenRouter (DESIGN.md §4), with retries, plus a local fake.

The rest of the backend only sees ``Provider.complete`` and ``ProviderError``.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1"
APP_TITLE = "GraftChat"

# Worth retrying: timeouts, rate limits and upstream failures.
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
BASE_DELAY_S = 1.0
MAX_DELAY_S = 20.0


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    model: str  # the model that actually answered
    input_tokens: int
    output_tokens: int
    cost: float  # USD, as reported by the provider; 0.0 when not reported


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    context_length: int | None


class ProviderError(Exception):
    """A call that failed for good (after retries).

    ``kind`` is one of ``auth``, ``rate_limit``, ``error``.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class Provider(Protocol):
    def complete(self, model: str, messages: Sequence[ChatMessage], *, tag: str = "chat") -> Completion:
        """Run one chat completion. ``tag`` says what the call is for (chat | takeaway)."""
        ...


class _Retry(Exception):
    """Internal: this attempt failed in a way worth retrying."""

    def __init__(self, error: ProviderError, wait: float | None = None) -> None:
        super().__init__(error.message)
        self.error = error
        self.wait = wait


def _error_message(body: object, fallback: str) -> str:
    """Pull the human-readable message out of an OpenRouter error body."""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        message = str(error.get("message") or fallback)
        metadata = error.get("metadata")
        if isinstance(metadata, dict) and metadata.get("raw"):
            message = f"{message} ({str(metadata['raw'])[:300]})"
        return message
    return fallback


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None


class OpenRouterProvider:
    """Chat completions through OpenRouter's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._sleep = sleep
        self._max_attempts = max_attempts

    def complete(self, model: str, messages: Sequence[ChatMessage], *, tag: str = "chat") -> Completion:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        last: ProviderError | None = None
        for attempt in range(self._max_attempts):
            try:
                return self._attempt(payload)
            except _Retry as retry:
                last = retry.error
                if attempt == self._max_attempts - 1:
                    break
                delay = min(MAX_DELAY_S, BASE_DELAY_S * 2**attempt) * (0.5 + random.random() / 2)
                if retry.wait is not None:
                    delay = min(MAX_DELAY_S, max(delay, retry.wait))
                self._sleep(delay)
        assert last is not None
        raise last

    def _attempt(self, payload: dict) -> Completion:
        try:
            response = self._client.post(
                f"{OPENROUTER_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}", "X-Title": APP_TITLE},
            )
        except httpx.TimeoutException as exc:
            raise _Retry(ProviderError("error", "OpenRouter did not answer in time.")) from exc
        except httpx.HTTPError as exc:
            raise _Retry(ProviderError("error", f"Could not reach OpenRouter: {exc}")) from exc

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            body = None

        status = response.status_code
        # OpenRouter can report an upstream failure inside a 200 response.
        if status == 200 and isinstance(body, dict) and isinstance(body.get("error"), dict):
            code = body["error"].get("code")
            status = code if isinstance(code, int) and code >= 400 else 502

        if status != 200:
            raise self._failure(status, body, response)

        try:
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise _Retry(ProviderError("error", "OpenRouter returned an unexpected response.")) from exc
        if isinstance(choice.get("error"), dict):
            message = _error_message({"error": choice["error"]}, "The model failed.")
            raise _Retry(ProviderError("error", message))
        if not isinstance(text, str) or not text.strip():
            raise _Retry(ProviderError("error", "The model returned an empty answer."))

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        cost = usage.get("cost")
        return Completion(
            text=text,
            model=str(body.get("model") or payload["model"]),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost=float(cost) if isinstance(cost, (int, float)) else 0.0,
        )

    def _failure(self, status: int, body: object, response: httpx.Response) -> Exception:
        message = _error_message(body, f"OpenRouter answered with HTTP {status}.")
        if status in (401, 403):
            return ProviderError("auth", f"OpenRouter rejected the API key: {message}")
        if status == 402:
            return ProviderError("error", f"OpenRouter refused the call (credits): {message}")
        if status == 429:
            error = ProviderError("rate_limit", f"Rate limited by OpenRouter: {message}")
            return _Retry(error, _retry_after(response))
        if status in RETRYABLE_STATUS:
            return _Retry(ProviderError("error", message), _retry_after(response))
        return ProviderError("error", message)


def _is_free(model: dict) -> bool:
    pricing = model.get("pricing")
    if not isinstance(pricing, dict):
        return False
    try:
        return float(pricing.get("prompt", 1)) == 0.0 and float(pricing.get("completion", 1)) == 0.0
    except (TypeError, ValueError):
        return False


def _outputs_text(model: dict) -> bool:
    architecture = model.get("architecture")
    if not isinstance(architecture, dict):
        return True
    outputs = architecture.get("output_modalities")
    return "text" in outputs if isinstance(outputs, list) else True


def fetch_free_models(client: httpx.Client | None = None) -> list[ModelInfo]:
    """The free text models OpenRouter currently lists (public endpoint, no key needed)."""
    client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    try:
        response = client.get(f"{OPENROUTER_URL}/models")
        response.raise_for_status()
        data = response.json()["data"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ProviderError("error", f"Could not load the model list from OpenRouter: {exc}") from exc

    models = []
    for model in data:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        if not (_is_free(model) and _outputs_text(model)):
            continue
        context = model.get("context_length")
        models.append(
            ModelInfo(
                id=model["id"],
                name=str(model.get("name") or model["id"]),
                context_length=context if isinstance(context, int) else None,
            )
        )
    return sorted(models, key=lambda m: m.name.lower())


class FakeProvider:
    """A canned model for UI work and demos (``GRAFTCHAT_FAKE_LLM=1``). No network, no cost."""

    MODEL = "fake/local"

    def complete(self, model: str, messages: Sequence[ChatMessage], *, tag: str = "chat") -> Completion:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if tag == "takeaway":
            text = json.dumps(
                [
                    {"title": "noted main point", "text": "The side conversation clarified the passage (fake take-away 1)."},
                    {"title": "added an example", "text": "A concrete example was worked through (fake take-away 2)."},
                    {"title": "open question", "text": "One detail is still open and worth revisiting (fake take-away 3)."},
                ]
            )
        else:
            topic = " ".join(last_user.split())[:80] or "that"
            text = (
                f"This is a fake answer about: {topic}\n\n"
                "1. **First point.** A short explanation you can select and branch from.\n"
                "2. **Second point.** Another passage, with some `inline code`.\n"
                "3. **Third point.** A final remark to follow up on.\n\n"
                f"(The model received {len(messages)} messages.)"
            )
        words_in = sum(len(m.content.split()) for m in messages)
        return Completion(
            text=text, model=self.MODEL, input_tokens=words_in, output_tokens=len(text.split()), cost=0.0
        )
