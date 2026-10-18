import json

import pytest
from fastapi.testclient import TestClient

from conftest import add_user, connect_agent, login, new_list, new_task

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def rpc(client, token, method, params=None, headers=None):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                           headers={**HEADERS, "Authorization": f"Bearer {token}", **(headers or {})})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["result"]


def call(client, token, tool, **arguments):
    """A tool's answer, or the error text for a tool error."""
    result = rpc(client, token, "tools/call", {"name": tool, "arguments": arguments})
    text = result["content"][0]["text"]
    return text if result["isError"] else json.loads(text)


@pytest.fixture
def token(client):
    """maria's agent; client is maria's browser."""
    return connect_agent(client)["access_token"]


def test_initialize_and_the_tools(client, token):
    result = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "test", "version": "1"}})
    assert result["serverInfo"]["name"] == "Taskly" and "complete_task" in result["instructions"]
    tools = {tool["name"]: tool for tool in rpc(client, token, "tools/list")["tools"]}
    assert set(tools) == {"list_lists", "list_tasks", "create_list", "add_tasks", "complete_task", "set_task_status",
                          "update_task", "delete_task"}
    assert tools["set_task_status"]["inputSchema"]["properties"]["status"]["enum"] == ["new", "progress", "done"]
    assert tools["list_tasks"]["annotations"]["readOnlyHint"] is True
    assert tools["add_tasks"]["annotations"]["destructiveHint"] is False
    assert tools["update_task"]["annotations"]["destructiveHint"] is False
    assert tools["delete_task"]["annotations"]["destructiveHint"] is True


def test_no_token_points_at_the_sign_in(anon):
    response = anon.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        'Bearer resource_metadata="http://testserver/.well-known/oauth-protected-resource/mcp", scope="tasks"')
    assert response.headers["cache-control"] == "no-store"


def test_a_bad_token_is_refused(anon):
    response = anon.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         headers={**HEADERS, "Authorization": "Bearer nonsense"})
    assert response.status_code == 401 and 'error="invalid_token"' in response.headers["www-authenticate"]


def test_a_token_is_for_this_address_only(client, token):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={**HEADERS, "Authorization": f"Bearer {token}", "Host": "other.example"})
    assert response.status_code == 401


def test_a_cross_site_request_is_refused(client, token):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={**HEADERS, "Authorization": f"Bearer {token}", "Origin": "https://evil.example"})
    assert response.status_code == 403


def test_a_trailing_slash_goes_to_the_address(client, token):
    response = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={**HEADERS, "Authorization": f"Bearer {token}"}, follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "http://testserver/mcp"


def test_a_disabled_user_is_cut_off(client, token, conn):
    conn.execute("UPDATE users SET disabled_at = '2026-01-01T00:00:00Z' WHERE username = 'maria'")
    conn.commit()
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers={**HEADERS, "Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_create_a_list_and_add_tasks(client, token):
    made = call(client, token, "create_list", name="  Weekend ")
    assert (made["name"], made["owner"], made["role"]) == ("Weekend", "maria", "owner")
    added = call(client, token, "add_tasks", list="weekend", titles=["Bake bread", " Call mum "])
    assert added["list"] == {"id": made["id"], "name": "Weekend"}
    assert [t["title"] for t in added["added"]] == ["Bake bread", "Call mum"]
    assert all(t["created_by"] == "maria" and not t["done"] for t in added["added"])
    # The page sees them on its next sync.
    [weekend] = client.get("/api/sync").json()["lists"]
    assert {t["title"] for t in weekend["tasks"]} == {"Bake bread", "Call mum"}


def test_lists_and_their_counts(client, token):
    groceries = new_list(client, "Groceries")
    milk = new_task(client, groceries["id"], "Milk")
    eggs = new_task(client, groceries["id"], "Eggs")
    new_task(client, groceries["id"], "Bread")
    client.patch(f"/api/tasks/{milk['id']}", json={"done": True})
    client.patch(f"/api/tasks/{eggs['id']}", json={"status": "progress"})
    [found] = call(client, token, "list_lists")["lists"]
    assert (found["id"], found["name"], found["open"], found["in_progress"], found["done"]) == (
        groceries["id"], "Groceries", 2, 1, 1)


def test_open_and_all_tasks(client, token):
    groceries, work = new_list(client, "Groceries"), new_list(client, "Work")
    milk = new_task(client, groceries["id"], "Milk")
    new_task(client, groceries["id"], "Eggs")
    new_task(client, work["id"], "Report")
    client.patch(f"/api/tasks/{milk['id']}", json={"done": True})

    every = call(client, token, "list_tasks")["lists"]
    assert {l["name"]: [t["title"] for t in l["tasks"]] for l in every} == {"Groceries": ["Eggs"], "Work": ["Report"]}
    [one] = call(client, token, "list_tasks", list=groceries["id"], include_done=True)["lists"]
    assert sorted(t["title"] for t in one["tasks"]) == ["Eggs", "Milk"]


def test_agents_see_due_dates(client, token):
    groceries = new_list(client)
    milk = new_task(client, groceries["id"], "Milk")
    new_task(client, groceries["id"], "Eggs")
    client.patch(f"/api/tasks/{milk['id']}", json={"due_date": "2026-10-17", "due_time": "15:00", "due_zone": "America/New_York"})
    [one] = call(client, token, "list_tasks", list=groceries["id"])["lists"]
    seen = {t["title"]: (t["due_date"], t["due_time"], t["due_zone"]) for t in one["tasks"]}
    assert seen == {"Milk": ("2026-10-17", "15:00", "America/New_York"), "Eggs": (None, None, None)}


def test_close_and_reopen_a_task(client, token):
    milk = new_task(client, new_list(client)["id"], "Milk")
    closed = call(client, token, "complete_task", task_id=milk["id"])
    assert (closed["status"], closed["done"], closed["done_by"]) == ("done", True, "maria")
    reopened = call(client, token, "complete_task", task_id=milk["id"], done=False)
    assert (reopened["status"], reopened["done"]) == ("new", False)


def test_set_a_tasks_status(client, token):
    milk = new_task(client, new_list(client)["id"], "Milk")
    started = call(client, token, "set_task_status", task_id=milk["id"], status="progress")
    assert (started["status"], started["done"]) == ("progress", False)
    # An in-progress task isn't finished, so done=false leaves it in progress.
    assert call(client, token, "complete_task", task_id=milk["id"], done=False)["status"] == "progress"
    finished = call(client, token, "set_task_status", task_id=milk["id"], status="done")
    assert (finished["status"], finished["done"], finished["done_by"]) == ("done", True, "maria")
    assert call(client, token, "set_task_status", task_id=milk["id"], status="new")["done_by"] is None
    assert "status" in call(client, token, "set_task_status", task_id=milk["id"], status="later")
    assert "No such task" in call(client, token, "set_task_status", task_id="not-an-id", status="done")


def test_rename_a_task(client, token):
    groceries = new_list(client)
    milk = new_task(client, groceries["id"], "Milk")
    renamed = call(client, token, "update_task", task_id=milk["id"], title="  Oat milk ")
    assert (renamed["id"], renamed["title"], renamed["status"]) == (milk["id"], "Oat milk", "new")
    assert client.get("/api/sync").json()["lists"][0]["tasks"][0]["title"] == "Oat milk"
    assert "title" in call(client, token, "update_task", task_id=milk["id"], title="  ")
    assert "title" in call(client, token, "update_task", task_id=milk["id"], title="x" * 501)
    assert "No such task" in call(client, token, "update_task", task_id="not-an-id", title="Eggs")


def test_delete_a_task(client, token):
    groceries = new_list(client)
    milk = new_task(client, groceries["id"], "Milk")
    bread = new_task(client, groceries["id"], "Bread")
    deleted = call(client, token, "delete_task", task_id=milk["id"])
    assert deleted["deleted"]["id"] == milk["id"] and deleted["deleted"]["title"] == "Milk"
    assert [t["id"] for t in client.get("/api/sync").json()["lists"][0]["tasks"]] == [bread["id"]]
    assert "No such task" in call(client, token, "delete_task", task_id=milk["id"])


def test_errors_are_tool_errors(client, token):
    assert "create_list makes one" in call(client, token, "list_tasks", list="Groceries")
    new_list(client, "Groceries")
    new_list(client, "Work")
    assert 'no list called "Shopping". Your lists: "Groceries", "Work"' in call(client, token, "add_tasks",
                                                                                list="Shopping", titles=["Milk"])
    assert "No such task" in call(client, token, "complete_task", task_id="not-an-id")
    assert "No such task" in call(client, token, "complete_task", task_id="00000000-0000-4000-8000-000000000000")
    assert "titles" in call(client, token, "add_tasks", list="Groceries", titles=[])
    assert "titles" in call(client, token, "add_tasks", list="Groceries", titles=["  "])
    assert "name" in call(client, token, "create_list", name="x" * 101)


def test_two_lists_with_one_name(client, token):
    first, second = new_list(client, "Groceries"), new_list(client, "groceries")
    error = call(client, token, "add_tasks", list="Groceries", titles=["Milk"])
    assert "2 lists are called" in error and first["id"] in error and second["id"] in error
    assert call(client, token, "add_tasks", list=second["id"], titles=["Milk"])["list"]["id"] == second["id"]


def test_the_agent_has_the_users_rights(app, settings, client, token):
    """maria's agent can't see tom's list; in a list tom shares with her, it works like a member."""
    add_user(settings, "tom")
    # Not `with`: a second lifespan would replace the running MCP session manager. tom only uses /api.
    tom = TestClient(app)
    login(tom, "tom")
    private = new_list(tom, "Tom's")
    secret = new_task(tom, private["id"], "Secret")
    shared = new_list(tom, "Shared")
    assert tom.post(f"/api/lists/{shared['id']}/members", json={"username": "maria"}).status_code == 201
    chore = new_task(tom, shared["id"], "Chore")

    assert [l["name"] for l in call(client, token, "list_lists")["lists"]] == ["Shared"]
    assert "no list called" in call(client, token, "list_tasks", list=private["id"])
    assert "No such task" in call(client, token, "complete_task", task_id=secret["id"])
    assert call(client, token, "complete_task", task_id=chore["id"])["done_by"] == "maria"
    assert "No such task" in call(client, token, "set_task_status", task_id=secret["id"], status="progress")
    assert call(client, token, "set_task_status", task_id=chore["id"], status="progress")["status"] == "progress"
    assert "No such task" in call(client, token, "update_task", task_id=secret["id"], title="Mine now")
    assert call(client, token, "update_task", task_id=chore["id"], title="Chores")["title"] == "Chores"
    assert "No such task" in call(client, token, "delete_task", task_id=secret["id"])
    assert call(client, token, "delete_task", task_id=chore["id"])["deleted"]["id"] == chore["id"]
    assert call(client, token, "add_tasks", list="shared", titles=["More"])["added"][0]["created_by"] == "maria"


def test_the_2026_protocol_works_too(client, token):
    """Stateless MCP (2026-07-28): no initialize, the version and capabilities ride on every request."""
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"}}
    new_list(client, "Groceries")
    result = rpc(client, token, "tools/call", {"name": "list_lists", "arguments": {}, "_meta": meta},
                 headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call", "Mcp-Name": "list_lists"})
    assert json.loads(result["content"][0]["text"])["lists"][0]["name"] == "Groceries"
