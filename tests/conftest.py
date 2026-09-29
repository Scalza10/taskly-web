import uuid

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
