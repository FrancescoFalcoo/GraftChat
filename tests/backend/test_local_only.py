"""The server answers only to this computer's own pages (DNS rebinding, cross-site POST)."""

from fastapi.testclient import TestClient

from api.app import create_app


def test_local_names_are_served(service):
    for base in ("http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"):
        client = TestClient(create_app(service), base_url=base)
        assert client.get("/api/health").status_code == 200


def test_a_foreign_host_name_is_refused(service):
    # A rebound domain resolves to 127.0.0.1 but keeps its own name in the Host header.
    client = TestClient(create_app(service), base_url="http://evil.example:8000")
    response = client.get("/api/conversations")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_local"


def test_a_post_from_another_website_is_refused(client):
    response = client.post("/api/conversations", json={}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    response = client.post("/api/conversations", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    response = client.post("/api/conversations", json={}, headers={"Origin": "null"})
    assert response.status_code == 403


def test_a_post_from_the_app_itself_is_accepted(client):
    for origin in ("http://127.0.0.1:8000", "http://localhost:5173"):
        response = client.post("/api/conversations", json={}, headers={"Origin": origin, "Sec-Fetch-Site": "same-origin"})
        assert response.status_code == 201


def test_reads_do_not_need_an_origin(client):
    assert client.get("/api/conversations", headers={"Origin": "https://evil.example"}).status_code == 200
