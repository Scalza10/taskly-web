from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import (CLAUDE_CALLBACK, VERIFIER, add_user, authorize_params, code_from, connect_agent,
                      register_agent)
from taskly.auth import LoginThrottle

MCP = "http://testserver/mcp"


def query(response) -> dict:
    assert response.status_code == 303, response.text
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}


def allow(client, client_id, **fields):
    return client.post("/oauth/authorize", data={**authorize_params(client_id), "action": "allow", **fields},
                       follow_redirects=False)


def swap(client, client_id, code, **extra):
    return client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                             "client_id": client_id, "redirect_uri": CLAUDE_CALLBACK,
                                             "code_verifier": VERIFIER, **extra})


def test_discovery_documents(anon):
    resource = anon.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == MCP
    assert resource["authorization_servers"] == ["http://testserver"]
    assert anon.get("/.well-known/oauth-protected-resource").json() == resource
    server = anon.get("/.well-known/oauth-authorization-server")
    assert server.headers["cache-control"] == "no-store"
    meta = server.json()
    assert meta["issuer"] == "http://testserver"
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["registration_endpoint"] == "http://testserver/oauth/register"
    assert meta["token_endpoint_auth_methods_supported"] == ["none"]


def test_the_address_follows_the_request(anon):
    meta = anon.get("/.well-known/oauth-protected-resource", headers={"host": "tasks.example"}).json()
    assert meta["resource"] == "http://tasks.example/mcp"


def test_register(anon):
    response = anon.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": [CLAUDE_CALLBACK],
                                                  "token_endpoint_auth_method": "client_secret_post"})
    assert response.status_code == 201
    body = response.json()
    assert body["client_id"] and "client_secret" not in body
    assert body["token_endpoint_auth_method"] == "none"


@pytest.mark.parametrize("body", [
    {"redirect_uris": ["https://evil.example/cb"]},
    {"redirect_uris": []},
    {"redirect_uris": [CLAUDE_CALLBACK] * 6},
    {"redirect_uris": "https://claude.ai/api/mcp/auth_callback"},
    {"redirect_uris": [CLAUDE_CALLBACK], "client_name": "x" * 101},
    ["not", "an", "object"],
])
def test_register_refuses(anon, body):
    response = anon.post("/oauth/register", json=body)
    assert response.status_code == 400
    assert response.json()["error"] in ("invalid_redirect_uri", "invalid_client_metadata")


def test_the_page_asks_for_a_password_without_a_session(anon):
    page = anon.get("/oauth/authorize", params=authorize_params(register_agent(anon)))
    assert page.status_code == 200
    assert 'name="password"' in page.text and "Claude" in page.text and "claude.ai" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["cache-control"] == "no-store"


def test_the_page_knows_who_is_logged_in(client):
    params = authorize_params(register_agent(client))
    page = client.get("/oauth/authorize", params=params)
    assert "Signed in as <strong>maria</strong>" in page.text and 'name="password"' not in page.text
    other = client.get("/oauth/authorize", params={**params, "account": "other"})
    assert 'name="password"' in other.text


def test_allow_with_the_browser_session(client):
    client_id = register_agent(client)
    response = swap(client, client_id, code_from(allow(client, client_id)))
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 3600 and body["scope"] == "tasks"
    assert body["access_token"] and body["refresh_token"]
    assert response.headers["cache-control"] == "no-store"


def test_allow_with_a_password(anon, settings):
    add_user(settings, "maria")
    tokens = connect_agent(anon)
    assert tokens["access_token"]
    assert "taskly_session" not in anon.cookies  # signing in for an agent doesn't log this browser in


def test_a_wrong_password_shows_the_page_again(anon, settings):
    add_user(settings, "maria")
    response = allow(anon, register_agent(anon), username="maria", password="wrong-password")
    assert response.status_code == 401
    assert "Wrong username or password" in response.text and 'name="password"' in response.text


def test_signing_in_for_an_agent_is_throttled(anon, app, settings):
    add_user(settings, "maria")
    client_id = register_agent(anon)
    app.state.login_throttle = LoginThrottle()
    for _ in range(10):
        assert allow(anon, client_id, username="maria", password="wrong-password").status_code == 401
    response = allow(anon, client_id, username="maria", password="correct-horse-battery")
    assert response.status_code == 401 and "Too many attempts" in response.text


def test_allow_without_a_session_or_password(anon):
    response = allow(anon, register_agent(anon))
    assert response.status_code == 401 and 'name="password"' in response.text


def test_cancel(client):
    response = client.post("/oauth/authorize", data={**authorize_params(register_agent(client)), "action": "cancel"},
                           follow_redirects=False)
    assert query(response)["error"] == "access_denied"
    assert query(response)["state"] == "s1"


def test_a_cross_site_post_is_refused(client):
    response = client.post("/oauth/authorize", data={**authorize_params(register_agent(client)), "action": "allow"},
                           headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert response.status_code == 403


def test_unknown_clients_and_redirects_are_not_followed(client):
    client_id = register_agent(client)
    page = client.get("/oauth/authorize", params=authorize_params("nope"))
    assert page.status_code == 400 and "location" not in page.headers
    page = client.get("/oauth/authorize", params=authorize_params(client_id, redirect_uri="https://evil.example/cb"))
    assert page.status_code == 400 and "location" not in page.headers
    page = client.get("/oauth/authorize", params=authorize_params(client_id, redirect_uri="https://claude.com/api/mcp/auth_callback"))
    assert page.status_code == 400  # allowed in general, but not registered by this client


@pytest.mark.parametrize("change, error", [
    ({"response_type": "token"}, "unsupported_response_type"),
    ({"code_challenge_method": "plain"}, "invalid_request"),
    ({"code_challenge": "short"}, "invalid_request"),
    ({"resource": "https://other.example/mcp"}, "invalid_target"),
])
def test_bad_requests_go_back_to_the_agent(client, change, error):
    page = client.get("/oauth/authorize", params={**authorize_params(register_agent(client)), **change},
                      follow_redirects=False)
    assert query(page)["error"] == error


def test_a_code_needs_its_verifier_and_works_once(client):
    client_id = register_agent(client)
    code = code_from(allow(client, client_id))
    assert swap(client, client_id, code, code_verifier="w" * 43).json()["error"] == "invalid_grant"
    assert swap(client, client_id, code).json()["error"] == "invalid_grant"  # gone after the wrong try
    code = code_from(allow(client, client_id))
    assert swap(client, client_id, code).status_code == 200
    assert swap(client, client_id, code).status_code == 400


def test_a_code_belongs_to_its_client_and_redirect(client):
    client_id, other = register_agent(client), register_agent(client)
    assert swap(client, other, code_from(allow(client, client_id))).json()["error"] == "invalid_grant"
    response = swap(client, client_id, code_from(allow(client, client_id)), redirect_uri="https://claude.com/x")
    assert response.json()["error"] == "invalid_grant"
    response = swap(client, client_id, code_from(allow(client, client_id)), resource="https://other.example/mcp")
    assert response.json()["error"] == "invalid_target"


def test_the_token_endpoint_knows_its_clients(anon):
    response = anon.post("/oauth/token", data={"grant_type": "authorization_code", "client_id": "nope"})
    assert response.status_code == 401 and response.json()["error"] == "invalid_client"
    response = anon.post("/oauth/token", data={"grant_type": "password", "client_id": register_agent(anon)})
    assert response.json()["error"] == "unsupported_grant_type"


def test_refresh(anon, settings):
    add_user(settings, "maria")
    tokens = connect_agent(anon)
    data = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": tokens["client_id"]}
    fresh = anon.post("/oauth/token", data=data)
    assert fresh.status_code == 200 and fresh.json()["refresh_token"] != tokens["refresh_token"]
    again = anon.post("/oauth/token", data=data)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


def test_the_client_may_authenticate_with_basic(anon, settings):
    add_user(settings, "maria")
    tokens = connect_agent(anon)
    response = anon.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
                         auth=(tokens["client_id"], ""))
    assert response.status_code == 200
