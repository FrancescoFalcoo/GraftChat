"""Setting up a key: checking it with OpenRouter and the OAuth PKCE login (docs/API.md)."""

from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from api.provider import KeyInfo, ProviderError, check_key, exchange_oauth_code

from .test_app import error_code


# --- checking a key when it is saved ------------------------------------------------------


def test_a_good_key_is_saved_with_what_openrouter_says(client, service):
    service._key_checker = lambda key: KeyInfo("my laptop", True, 50, 42)
    body = client.put("/api/settings", json={"api_key": "sk-or-v1-good-key-123456"}).json()
    assert body["has_api_key"] is True
    assert body["key_info"] == {
        "label": "my laptop",
        "is_free_tier": True,
        "free_daily_limit": 50,
        "free_daily_remaining": 42,
    }


def test_a_rejected_key_is_not_saved(client, service):
    def reject(key):
        raise ProviderError("auth", "invalid key")

    service._key_checker = reject
    response = client.put("/api/settings", json={"api_key": "sk-or-v1-wrong"})
    assert response.status_code == 422 and error_code(response) == "validation"
    assert "rejected" in response.json()["error"]["message"]
    assert service.settings.load().api_key != "sk-or-v1-wrong"


def test_a_key_is_saved_when_openrouter_cannot_be_reached(client, service):
    def offline(key):
        raise ProviderError("error", "no network")

    service._key_checker = offline
    body = client.put("/api/settings", json={"api_key": "sk-or-v1-offline-123456"}).json()
    assert body["has_api_key"] is True and body["key_info"] is None


def test_check_key_reads_the_key_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={"data": {"label": "x", "is_free_tier": False, "free_model_daily_requests": {"limit": 1000, "remaining": 990}}},
        )

    info = check_key("sk-test", httpx.Client(transport=httpx.MockTransport(handler)))
    assert info == KeyInfo("x", False, 1000, 990)
    assert seen[0].url == "https://openrouter.ai/api/v1/key"
    assert seen[0].headers["authorization"] == "Bearer sk-test"


def test_check_key_maps_401_to_auth():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "bad"}}))
    with pytest.raises(ProviderError) as caught:
        check_key("sk-test", httpx.Client(transport=transport))
    assert caught.value.kind == "auth"


# --- OAuth PKCE -----------------------------------------------------------------------------


def start(client):
    url = client.post("/api/oauth/start").json()["url"]
    query = parse_qs(urlparse(url).query)
    callback = urlparse(query["callback_url"][0])
    return url, query, callback, parse_qs(callback.query)["state"][0]


def test_start_sends_the_user_to_openrouter_with_a_challenge(client):
    url, query, callback, _ = start(client)
    assert url.startswith("https://openrouter.ai/auth?")
    assert query["code_challenge_method"] == ["S256"]
    assert callback.path == "/api/oauth/callback"
    assert callback.hostname in ("testserver", "127.0.0.1", "localhost")


def test_callback_exchanges_the_code_saves_the_key_and_goes_home(client, service):
    verifiers = []

    def exchange(code, verifier):
        verifiers.append(verifier)
        return "sk-or-v1-from-login-0042"

    service._oauth_exchanger = exchange
    _, query, _, state = start(client)
    response = client.get(f"/api/oauth/callback?code=abc&state={state}", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/?openrouter=connected"
    assert service.settings.load().api_key == "sk-or-v1-from-login-0042"
    # the verifier sent to OpenRouter matches the challenge of the start URL
    digest = hashlib.sha256(verifiers[0].encode()).digest()
    assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == query["code_challenge"][0]


def test_callback_with_an_unknown_state_saves_nothing(client, service):
    before = service.settings.load().api_key
    response = client.get("/api/oauth/callback?code=abc&state=forged", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?openrouter=error&message=")
    assert service.settings.load().api_key == before


def test_a_state_works_only_once(client):
    _, _, _, state = start(client)
    client.get(f"/api/oauth/callback?code=abc&state={state}", follow_redirects=False)
    again = client.get(f"/api/oauth/callback?code=abc&state={state}", follow_redirects=False)
    assert "error" in again.headers["location"]


def test_exchange_posts_the_code_and_the_verifier():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"key": "sk-or-v1-new"})

    key = exchange_oauth_code("c0de", "v3rifier", httpx.Client(transport=httpx.MockTransport(handler)))
    assert key == "sk-or-v1-new"
    assert seen == [{"code": "c0de", "code_verifier": "v3rifier", "code_challenge_method": "S256"}]
