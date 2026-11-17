"""LLM provider client: OpenRouter (DESIGN.md §4), with retries, plus a local fake.

The rest of the backend only sees ``Provider.complete`` and ``ProviderError``.
"""

from __future__ import annotations

import base64
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
class ImagePart:
    """An image sent with a message. ``ref`` names it in the call log (``attachment:<id>``)."""

    mime: str
    data: bytes
    ref: str


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str
    images: tuple[ImagePart, ...] = ()


def message_payload(message: ChatMessage, *, inline_images: bool = True) -> dict:
    """One message in OpenRouter's (OpenAI-compatible) format.

    A message with images becomes a list of parts: the text, then one
    ``image_url`` part per image, as a base64 data URL. With
    ``inline_images=False`` each URL is the image's ``ref`` instead: that is the
    form stored in the call log, which keeps the log readable and small while
    still saying exactly which image was sent where.
    """
    if not message.images:
        return {"role": message.role, "content": message.content}
    parts: list[dict] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for image in message.images:
        if inline_images:
            url = f"data:{image.mime};base64,{base64.b64encode(image.data).decode('ascii')}"
        else:
            url = image.ref
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return {"role": message.role, "content": parts}


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
    images: bool = False  # the model accepts images as input


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
            "messages": [message_payload(m) for m in messages],
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


@dataclass(frozen=True)
class KeyInfo:
    """What OpenRouter says about a key (``GET /api/v1/key``)."""

    label: str | None
    is_free_tier: bool  # the account never bought credits
    free_daily_limit: int | None  # requests per day to ":free" models
    free_daily_remaining: int | None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def check_key(api_key: str, client: httpx.Client | None = None) -> KeyInfo:
    """Ask OpenRouter whether ``api_key`` works, and what it allows.

    Raises:
        ProviderError: ``auth`` if the key is rejected, ``error`` if OpenRouter
            cannot be reached or answers something unexpected.
    """
    client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0))
    try:
        response = client.get(f"{OPENROUTER_URL}/key", headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        raise ProviderError("error", f"Could not reach OpenRouter to check the key: {exc}") from exc
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = None
    if response.status_code in (401, 403):
        raise ProviderError("auth", _error_message(body, "OpenRouter rejected this key."))
    if response.status_code != 200 or not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise ProviderError("error", _error_message(body, f"OpenRouter answered with HTTP {response.status_code}."))
    data = body["data"]
    daily = data.get("free_model_daily_requests")
    daily = daily if isinstance(daily, dict) else {}
    label = data.get("label")
    return KeyInfo(
        label=label if isinstance(label, str) else None,
        is_free_tier=bool(data.get("is_free_tier")),
        free_daily_limit=_int_or_none(daily.get("limit")),
        free_daily_remaining=_int_or_none(daily.get("remaining")),
    )


OAUTH_URL = "https://openrouter.ai/auth"


def exchange_oauth_code(code: str, code_verifier: str, client: httpx.Client | None = None) -> str:
    """Turn the code of OpenRouter's OAuth PKCE flow into the user's API key.

    Raises:
        ProviderError: if the exchange fails (expired or used code, network).
    """
    client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    try:
        response = client.post(
            f"{OPENROUTER_URL}/auth/keys",
            json={"code": code, "code_verifier": code_verifier, "code_challenge_method": "S256"},
        )
    except httpx.HTTPError as exc:
        raise ProviderError("error", f"Could not reach OpenRouter: {exc}") from exc
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = None
    key = body.get("key") if isinstance(body, dict) else None
    if response.status_code != 200 or not isinstance(key, str) or not key:
        message = _error_message(body, f"OpenRouter answered with HTTP {response.status_code}.")
        raise ProviderError("auth", f"OpenRouter did not give a key: {message}")
    return key


def _is_free(model: dict) -> bool:
    pricing = model.get("pricing")
    if not isinstance(pricing, dict):
        return False
    try:
        return float(pricing.get("prompt", 1)) == 0.0 and float(pricing.get("completion", 1)) == 0.0
    except (TypeError, ValueError):
        return False


def _outputs_text_only(model: dict) -> bool:
    """True for chat models: the output is text and nothing else (no audio or image generators)."""
    architecture = model.get("architecture")
    if not isinstance(architecture, dict):
        return True
    outputs = architecture.get("output_modalities")
    return outputs == ["text"] if isinstance(outputs, list) else True


def _accepts_images(model: dict) -> bool:
    architecture = model.get("architecture")
    if not isinstance(architecture, dict):
        return False
    inputs = architecture.get("input_modalities")
    return isinstance(inputs, list) and "image" in inputs


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
        if not (_is_free(model) and _outputs_text_only(model)):
            continue
        context = model.get("context_length")
        models.append(
            ModelInfo(
                id=model["id"],
                name=str(model.get("name") or model["id"]),
                context_length=context if isinstance(context, int) else None,
                images=_accepts_images(model),
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
                f"(The model received {len(messages)} messages"
                + (f" and {images} images" if (images := sum(len(m.images) for m in messages)) else "")
                + ".)"
            )
        words_in = sum(len(m.content.split()) for m in messages)
        return Completion(
            text=text, model=self.MODEL, input_tokens=words_in, output_tokens=len(text.split()), cost=0.0
        )
