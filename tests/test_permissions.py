"""Who may do what: every list and task endpoint, for the owner, a member, someone outside
the list, and someone not logged in."""

import uuid
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from conftest import add_user, login, new_list, new_task

ROLES = ["owner", "member", "outsider", "anonymous"]

# (name, method, path, body, expected status per role). {list} and {task} are filled in.
CASES = [
    ("sync", "GET", "/api/sync", None, {"owner": 200, "member": 200, "outsider": 200, "anonymous": 401}),
    ("rename list", "PATCH", "/api/lists/{list}", {"name": "Food"}, {"owner": 200, "member": 403, "outsider": 404, "anonymous": 401}),
    ("delete list", "DELETE", "/api/lists/{list}", None, {"owner": 204, "member": 403, "outsider": 404, "anonymous": 401}),
    ("add member", "POST", "/api/lists/{list}/members", {"username": "bob"}, {"owner": 201, "member": 403, "outsider": 404, "anonymous": 401}),
    ("remove zoe", "DELETE", "/api/lists/{list}/members/zoe", None, {"owner": 204, "member": 403, "outsider": 404, "anonymous": 401}),
    ("create task", "POST", "/api/tasks", {"id": "{new}", "list_id": "{list}", "title": "x"}, {"owner": 201, "member": 201, "outsider": 404, "anonymous": 401}),
    ("tick task", "PATCH", "/api/tasks/{task}", {"done": True}, {"owner": 200, "member": 200, "outsider": 404, "anonymous": 401}),
    ("delete task", "DELETE", "/api/tasks/{task}", None, {"owner": 204, "member": 204, "outsider": 404, "anonymous": 401}),
]


@pytest.fixture
def world(app, settings):
    """maria owns Groceries with tom and zoe as members and one task; ann is in no list; bob exists."""
    for name in ["maria", "tom", "zoe", "ann", "bob"]:
        add_user(settings, name)
    with ExitStack() as stack:
        clients = {}
        for role, name in [("owner", "maria"), ("member", "tom"), ("outsider", "ann")]:
            clients[role] = stack.enter_context(TestClient(app))
            login(clients[role], name)
        clients["anonymous"] = stack.enter_context(TestClient(app))
        groceries = new_list(clients["owner"])
        for name in ["tom", "zoe"]:
            clients["owner"].post(f"/api/lists/{groceries['id']}/members", json={"username": name})
        task = new_task(clients["owner"], groceries["id"])
        yield clients, {"list": groceries["id"], "task": task["id"]}


def fill(value, ids):
    if isinstance(value, dict):
        return {k: fill(v, ids) for k, v in value.items()}
    if isinstance(value, str):
        return value.format(new=str(uuid.uuid4()), **ids)
    return value


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("name, method, path, body, expected", CASES, ids=[c[0] for c in CASES])
def test_permissions(world, role, name, method, path, body, expected):
    clients, ids = world
    response = clients[role].request(method, fill(path, ids), json=fill(body, ids))
    assert response.status_code == expected[role], response.text


def test_outsiders_see_nothing_in_sync(world):
    clients, _ = world
    assert clients["outsider"].get("/api/sync").json() == {"me": "ann", "lists": []}
