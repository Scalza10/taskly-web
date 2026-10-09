import base64
import hashlib
from datetime import timedelta

import pytest

from taskly import oauth, users

RESOURCE = "http://testserver/mcp"
CLAUDE = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture
def maria(conn):
    return users.create_user(conn, "maria", "correct-horse-battery")


@pytest.fixture
def claude(conn):
    return oauth.register_client(conn, "Claude", [CLAUDE])


def challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def grant(conn, client, user, resource=RESOURCE) -> dict:
    code = oauth.create_code(conn, client_id=client["id"], user_id=user["id"], redirect_uri=CLAUDE,
                             code_challenge=challenge("v" * 43), resource=resource)
    return oauth.create_grant(conn, oauth.take_code(conn, code))


@pytest.mark.parametrize("uri", [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:53682/callback",
    "http://127.0.0.1/callback",
    "https://oauth-redirect.googleusercontent.com/r/gemini",
    "https://oauth-redirect-2.googleusercontent.com/cb",
    "https://antigravity.google/oauth-callback",
])
def test_known_agents_may_register(uri):
    assert oauth.redirect_allowed(uri)


@pytest.mark.parametrize("uri", [
    "https://evil.example/callback",
    "https://claude.ai/somewhere-else",
    "http://claude.ai/api/mcp/auth_callback",
    "https://localhost/callback",
    "http://localhost.evil.example/cb",
    "https://oauth-redirect.googleusercontent.com.evil.example/cb",
    "https://evil.googleusercontent.com/cb",
    "http://oauth-redirect.googleusercontent.com/cb",
    "https://oauth-redirect.googleusercontent.com:8443/cb",
    "http://localhost:99999/cb",
    "http://localhost/cb#fragment",
    "javascript:alert(1)",
    "",
])
def test_other_redirects_are_refused(uri):
    assert not oauth.redirect_allowed(uri)


def test_a_loopback_redirect_matches_on_any_port():
    registered = ["http://localhost:1234/callback"]
    assert oauth.redirect_matches(registered, "http://localhost:5555/callback")
    assert not oauth.redirect_matches(registered, "http://localhost:5555/other")
    assert not oauth.redirect_matches(registered, "http://127.0.0.1:1234/callback")
    assert oauth.redirect_matches([CLAUDE], CLAUDE)
    assert not oauth.redirect_matches([CLAUDE], CLAUDE + "?x=1")


def test_pkce():
    assert oauth.pkce_ok("v" * 43, challenge("v" * 43))
    assert not oauth.pkce_ok("w" * 43, challenge("v" * 43))


def test_a_code_works_once(conn, claude, maria):
    code = oauth.create_code(conn, client_id=claude["id"], user_id=maria["id"], redirect_uri=CLAUDE,
                             code_challenge="c", resource=RESOURCE)
    row = oauth.take_code(conn, code)
    assert (row["client_id"], row["user_id"], row["redirect_uri"], row["resource"]) == (
        claude["id"], maria["id"], CLAUDE, RESOURCE)
    assert oauth.take_code(conn, code) is None


def test_an_expired_code_is_refused(conn, claude, maria, monkeypatch):
    monkeypatch.setattr(oauth, "CODE_LIFETIME", timedelta(seconds=-1))
    code = oauth.create_code(conn, client_id=claude["id"], user_id=maria["id"], redirect_uri=CLAUDE,
                             code_challenge="c", resource=RESOURCE)
    assert oauth.take_code(conn, code) is None


def test_an_access_token_names_its_user_for_its_resource_only(conn, claude, maria):
    tokens = grant(conn, claude, maria)
    assert oauth.token_user(conn, tokens["access_token"], RESOURCE) == {"id": maria["id"], "username": "maria"}
    assert oauth.token_user(conn, tokens["access_token"], "https://other/mcp") is None
    assert oauth.token_user(conn, tokens["refresh_token"], RESOURCE) is None
    assert oauth.token_user(conn, "nonsense", RESOURCE) is None


def test_an_expired_access_token_is_refused(conn, claude, maria, monkeypatch):
    monkeypatch.setattr(oauth, "ACCESS_LIFETIME", timedelta(seconds=-1))
    tokens = grant(conn, claude, maria)
    assert oauth.token_user(conn, tokens["access_token"], RESOURCE) is None


def test_a_refresh_token_is_replaced_when_used(conn, claude, maria):
    first = grant(conn, claude, maria)
    second = oauth.refresh(conn, first["refresh_token"], claude["id"])
    assert second["refresh_token"] != first["refresh_token"]
    assert oauth.token_user(conn, second["access_token"], RESOURCE)["username"] == "maria"
    assert oauth.refresh(conn, first["refresh_token"], claude["id"]) is None
    assert oauth.refresh(conn, second["access_token"], claude["id"]) is None


def test_a_refresh_token_belongs_to_its_client(conn, claude, maria):
    other = oauth.register_client(conn, "Other", [CLAUDE])
    tokens = grant(conn, claude, maria)
    assert oauth.refresh(conn, tokens["refresh_token"], other["id"]) is None
    assert oauth.refresh(conn, tokens["refresh_token"], claude["id"]) is not None


def test_a_disabled_user_is_disconnected(conn, claude, maria):
    tokens = grant(conn, claude, maria)
    users.set_disabled(conn, maria["id"], True)
    assert oauth.token_user(conn, tokens["access_token"], RESOURCE) is None
    assert oauth.refresh(conn, tokens["refresh_token"], claude["id"]) is None


def test_delete_user_grants(conn, claude, maria):
    tom = users.create_user(conn, "tom", "correct-horse-battery")
    mine, his = grant(conn, claude, maria), grant(conn, claude, tom)
    assert oauth.delete_user_grants(conn, maria["id"]) == 1
    assert oauth.token_user(conn, mine["access_token"], RESOURCE) is None
    assert oauth.refresh(conn, mine["refresh_token"], claude["id"]) is None
    assert oauth.token_user(conn, his["access_token"], RESOURCE)["username"] == "tom"


def test_unused_clients_are_pruned_after_a_day(conn, claude, maria):
    used = oauth.register_client(conn, "Used", [CLAUDE])
    grant(conn, used, maria)
    conn.execute("UPDATE oauth_clients SET created_at = '2020-01-01T00:00:00Z'")
    conn.commit()
    oauth.register_client(conn, "New", [CLAUDE])
    assert oauth.get_client(conn, claude["id"]) is None
    assert oauth.get_client(conn, used["id"]) is not None
