import base64
import hashlib
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from contextlib import closing
from fastapi.testclient import TestClient

from taskly.main import create_app
from taskly.settings import Settings
from taskly import passwords, db, users


def make_settings(tmp_path, **overrides) -> Settings:
    """Settings on a fresh database in tmp_path. _env_file=None keeps a local .env out of tests.
    static_dir points at tmp_path/static, which exists only if a test creates it."""
    values = {"db_path": str(tmp_path / "taskly.db"), "static_dir": str(tmp_path / "static")}
    return Settings(_env_file=None, **{**values, **overrides})


PASSWORD = "correct-horse-battery"


def add_user(settings, username, password=PASSWORD) -> dict:
    """Create an account straight in the database, as `taskly.admin add-user` would."""
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        return users.create_user(conn, username, password)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def app(settings):
    return create_app(settings)


def login(client, username, password=PASSWORD):
    response = client.post("/api/login", json={"username": username, "password": password})
    assert response.status_code == 204, response.text
    return response


@pytest.fixture
def anon(app):
    """A browser that hasn't logged in."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(app, settings):
    """A browser logged in as maria."""
    add_user(settings, "maria")
    with TestClient(app) as client:
        login(client, "maria")
        yield client


@pytest.fixture
def conn(settings):
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        yield conn


@pytest.fixture(autouse=True)
def fast_passwords(monkeypatch):
    """scrypt at full cost takes ~100 ms per hash; tests hash a lot. test_passwords checks the real cost.
    Also lowers the dummy hash cost so unknown username logins in tests are fast."""
    monkeypatch.setattr(passwords, "N", 2**4)
    monkeypatch.setattr(passwords, "DUMMY_HASH", passwords.hash_password("dummy"))


def new_list(client, name="Groceries") -> dict:
    response = client.post("/api/lists", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def new_task(client, list_id, title="Milk") -> dict:
    response = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": list_id, "title": title})
    assert response.status_code == 201, response.text
    return response.json()


CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 43


def pkce_challenge(verifier: str = VERIFIER) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def register_agent(client, redirect_uri=CLAUDE_CALLBACK) -> str:
    response = client.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": [redirect_uri]})
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def authorize_params(client_id, redirect_uri=CLAUDE_CALLBACK, **extra) -> dict:
    return {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": "s1",
            "code_challenge": pkce_challenge(), "code_challenge_method": "S256",
            "resource": "http://testserver/mcp", **extra}


def code_from(response) -> str:
    assert response.status_code == 303, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["state"] == ["s1"] and query["iss"] == ["http://testserver"], query
    return query["code"][0]


def connect_agent(client, username="maria", password=PASSWORD) -> dict:
    """What Claude does to connect: register, sign in on the page, swap the code for tokens."""
    client_id = register_agent(client)
    response = client.post("/oauth/authorize", data={**authorize_params(client_id), "action": "allow",
                                                     "username": username, "password": password},
                           follow_redirects=False)
    response = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code_from(response),
                                                 "client_id": client_id, "redirect_uri": CLAUDE_CALLBACK,
                                                 "code_verifier": VERIFIER, "resource": "http://testserver/mcp"})
    assert response.status_code == 200, response.text
    return {**response.json(), "client_id": client_id}
