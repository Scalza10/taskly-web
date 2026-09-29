import uuid

from fastapi.testclient import TestClient

from conftest import add_user, login, make_settings, new_list, new_task
from taskly.main import create_app


def sync(client):
    response = client.get("/api/sync")
    assert response.status_code == 200
    return response.json()


def test_a_new_user_sees_no_lists(client):
    assert sync(client) == {"me": "maria", "lists": []}


def test_create_list(client):
    made = new_list(client, "  Groceries  ")
    assert (made["name"], made["owner"], made["role"], made["members"]) == ("Groceries", "maria", "owner", ["maria"])
    assert [l["name"] for l in sync(client)["lists"]] == ["Groceries"]


def test_list_names_are_checked(client):
    assert client.post("/api/lists", json={"name": "  "}).status_code == 422
    assert client.post("/api/lists", json={"name": "x" * 101}).status_code == 422


def test_rename_and_delete_list(client):
    made = new_list(client)
    new_task(client, made["id"])
    assert client.patch(f"/api/lists/{made['id']}", json={"name": "Food"}).json()["name"] == "Food"
    assert client.delete(f"/api/lists/{made['id']}").status_code == 204
    assert sync(client)["lists"] == []
    assert client.delete(f"/api/lists/{made['id']}").status_code == 404


def test_adding_members(client, settings):
    add_user(settings, "tom")
    add_user(settings, "ann")
    made = new_list(client)
    url = f"/api/lists/{made['id']}/members"

    first = client.post(url, json={"username": "TOM"})
    assert first.status_code == 201
    assert first.json()["members"] == ["maria", "tom"]
    assert client.post(url, json={"username": "tom"}).status_code == 200
    assert client.post(url, json={"username": "nobody"}).status_code == 404

    from contextlib import closing
    from taskly import db, users
    with closing(db.connect(settings.db_path)) as conn:
        users.set_disabled(conn, users.find_user(conn, "ann")["id"], True)
    assert client.post(url, json={"username": "ann"}).json()["detail"] == "No such user"


def test_leaving_and_removing(app, client, settings):
    add_user(settings, "tom")
    made = new_list(client)
    client.post(f"/api/lists/{made['id']}/members", json={"username": "tom"})

    assert client.delete(f"/api/lists/{made['id']}/members/maria").status_code == 409
    with TestClient(app) as tom:
        login(tom, "tom")
        assert tom.delete(f"/api/lists/{made['id']}/members/tom").status_code == 204
        assert sync(tom)["lists"] == []
        assert tom.patch(f"/api/tasks/{uuid.uuid4()}", json={"done": True}).status_code == 404
    assert client.delete(f"/api/lists/{made['id']}/members/tom").status_code == 404


def test_removed_members_lose_access_at_once(app, client, settings):
    add_user(settings, "tom")
    made = new_list(client)
    task = new_task(client, made["id"])
    client.post(f"/api/lists/{made['id']}/members", json={"username": "tom"})
    with TestClient(app) as tom:
        login(tom, "tom")
        assert tom.patch(f"/api/tasks/{task['id']}", json={"done": True}).status_code == 200
        assert client.delete(f"/api/lists/{made['id']}/members/tom").status_code == 204
        assert tom.patch(f"/api/tasks/{task['id']}", json={"done": False}).status_code == 404
        assert sync(tom)["lists"] == []


def test_create_task(client):
    made = new_list(client)
    task_id = str(uuid.uuid4())
    response = client.post("/api/tasks", json={"id": task_id, "list_id": made["id"], "title": "  Milk "})
    assert response.status_code == 201
    task = response.json()
    assert (task["id"], task["list_id"], task["title"], task["done"]) == (task_id, made["id"], "Milk", False)
    assert (task["created_by"], task["done_by"]) == ("maria", None)


def test_a_retried_create_changes_nothing(client):
    made = new_list(client)
    task = new_task(client, made["id"], "Milk")
    again = client.post("/api/tasks", json={"id": task["id"], "list_id": made["id"], "title": "Oat milk"})
    assert again.status_code == 200
    assert again.json()["title"] == "Milk"
    assert len(sync(client)["lists"][0]["tasks"]) == 1


def test_the_same_id_in_another_list_is_a_conflict(client):
    first, second = new_list(client, "A"), new_list(client, "B")
    task = new_task(client, first["id"])
    clash = client.post("/api/tasks", json={"id": task["id"], "list_id": second["id"], "title": "x"})
    assert clash.status_code == 409


def test_task_input_is_checked(client):
    made = new_list(client)
    assert client.post("/api/tasks", json={"id": "7", "list_id": made["id"], "title": "x"}).status_code == 422
    assert client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": " "}).status_code == 422
    assert client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x" * 501}).status_code == 422
    unknown_list = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": str(uuid.uuid4()), "title": "x"})
    assert unknown_list.status_code == 404


def test_update_and_delete_task(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    done = client.patch(f"/api/tasks/{task['id']}", json={"done": True}).json()
    assert (done["done"], done["done_by"], done["title"]) == (True, "maria", "Milk")
    assert client.patch(f"/api/tasks/{task['id']}", json={"title": "Oat milk"}).json()["done"] is True
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert client.patch(f"/api/tasks/{task['id']}", json={"done": False}).status_code == 404


def test_sync_sorts_lists_by_name_and_tasks_open_first(client):
    new_list(client, "zoo")
    food = new_list(client, "Food")
    first = new_task(client, food["id"], "first")
    new_task(client, food["id"], "second")
    client.patch(f"/api/tasks/{first['id']}", json={"done": True})
    seen = sync(client)
    assert [l["name"] for l in seen["lists"]] == ["Food", "zoo"]
    assert [t["title"] for t in seen["lists"][0]["tasks"]] == ["second", "first"]


def test_lists_survive_a_restart(settings):
    add_user(settings, "maria")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        new_task(client, new_list(client)["id"], "still here")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        assert [t["title"] for t in sync(client)["lists"][0]["tasks"]] == ["still here"]


def test_lone_surrogates_are_422_not_500(client):
    made = new_list(client)
    json_type = {"Content-Type": "application/json"}
    task = client.post("/api/tasks", content='{"id": "%s", "list_id": "%s", "title": "\\ud800"}' % (uuid.uuid4(), made["id"]), headers=json_type)
    assert task.status_code == 422
    named = client.post("/api/lists", content='{"name": "\\ud800"}', headers=json_type)
    assert named.status_code == 422


def test_member_names_are_checked_before_any_query(client):
    made = new_list(client)
    url = f"/api/lists/{made['id']}/members"
    lone = client.post(url, content='{"username": "\\ud800"}', headers={"Content-Type": "application/json"})
    assert (lone.status_code, lone.json()["detail"]) == (404, "No such user")
    long = client.post(url, json={"username": "x" * 10000})
    assert (long.status_code, long.json()["detail"]) == (404, "No such user")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_page_and_its_files_are_served(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Taskly</title>")
    (static / "assets").mkdir()
    (static / "assets" / "index-abc123.js").write_text("export {};")
    (static / "assets" / "index-abc123.css").write_text("body {}")
    (static / "manifest.webmanifest").write_text("{}")

    with TestClient(create_app(make_settings(tmp_path, static_dir=str(static)))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "<title>Taskly</title>" in page.text
        assert page.headers["cache-control"] == "no-cache"
        assert "cache-control" not in client.get("/assets/index-abc123.js").headers
        assert client.get("/assets/index-abc123.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/assets/index-abc123.css").headers["content-type"].startswith("text/css")
        assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")


def test_api_runs_without_a_built_page(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404


def test_api_docs_are_off_unless_asked_for(client, tmp_path):
    # With Caddy's password gone they would be public, and /docs loads its viewer from a CDN.
    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404
    with TestClient(create_app(make_settings(tmp_path / "local", api_docs=True))) as local:
        assert local.get("/docs").status_code == 200
        assert local.get("/openapi.json").status_code == 200


def vanish_after_role_check(monkeypatch, conn, list_id):
    """Delete the list right after the route's role check passes: another device won the race."""
    from taskly import lists, routes

    real = routes.require_role

    def check_then_delete(*args, **kwargs):
        role = real(*args, **kwargs)
        lists.delete_list(conn, list_id)
        return role

    monkeypatch.setattr(routes, "require_role", check_then_delete)


def test_a_task_deleted_mid_update_is_a_404(client, conn, monkeypatch):
    from taskly import tasks

    task = new_task(client, new_list(client)["id"])
    real = tasks.update_task

    def delete_then_update(*args, **kwargs):
        tasks.delete_task(conn, task["id"])
        return real(*args, **kwargs)

    monkeypatch.setattr(tasks, "update_task", delete_then_update)
    response = client.patch(f"/api/tasks/{task['id']}", json={"done": True})
    assert (response.status_code, response.json()["detail"]) == (404, "No such task")


def test_a_list_deleted_mid_create_is_a_404(client, conn, monkeypatch):
    list_id = new_list(client)["id"]
    vanish_after_role_check(monkeypatch, conn, list_id)
    response = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": list_id, "title": "Milk"})
    assert (response.status_code, response.json()["detail"]) == (404, "No such list")


def test_a_list_deleted_mid_rename_is_a_404(client, conn, monkeypatch):
    list_id = new_list(client)["id"]
    vanish_after_role_check(monkeypatch, conn, list_id)
    response = client.patch(f"/api/lists/{list_id}", json={"name": "Other"})
    assert (response.status_code, response.json()["detail"]) == (404, "No such list")


def test_a_list_deleted_mid_add_member_is_a_404(client, conn, settings, monkeypatch):
    add_user(settings, "joao")
    list_id = new_list(client)["id"]
    vanish_after_role_check(monkeypatch, conn, list_id)
    response = client.post(f"/api/lists/{list_id}/members", json={"username": "joao"})
    assert (response.status_code, response.json()["detail"]) == (404, "No such list")
