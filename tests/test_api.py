from fastapi.testclient import TestClient

from taskly.main import create_app
from conftest import add_user, login, make_settings


def add(client, title="Buy milk"):
    response = client.post("/api/todos", json={"title": title})
    assert response.status_code == 201
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_starts_empty(client):
    assert client.get("/api/todos").json() == []


def test_create_returns_the_todo(client):
    todo = add(client, "  Buy milk  ")
    assert todo["title"] == "Buy milk"
    assert todo["done"] is False
    assert isinstance(todo["id"], int)
    assert todo["created_at"].endswith("Z")


def test_blank_or_too_long_title_is_rejected(client):
    assert client.post("/api/todos", json={"title": "   "}).status_code == 422
    assert client.post("/api/todos", json={"title": "x" * 501}).status_code == 422
    assert client.post("/api/todos", json={}).status_code == 422
    # A lone surrogate is valid JSON that httpx can't send itself; it must be a 422, not a 500.
    lone = client.post("/api/todos", content='{"title": "\\ud800"}', headers={"Content-Type": "application/json"})
    assert lone.status_code == 422


def test_list_puts_open_todos_first_then_newest(client):
    first = add(client, "first")
    second = add(client, "second")
    third = add(client, "third")
    client.patch(f"/api/todos/{third['id']}", json={"done": True})

    titles = [todo["title"] for todo in client.get("/api/todos").json()]
    assert titles == ["second", "first", "third"]
    assert first["id"] < second["id"]


def test_patch_changes_only_given_fields(client):
    todo = add(client, "Buy milk")

    done = client.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()
    assert done["done"] is True
    assert done["title"] == "Buy milk"

    renamed = client.patch(f"/api/todos/{todo['id']}", json={"title": "Buy oat milk"}).json()
    assert renamed["title"] == "Buy oat milk"
    assert renamed["done"] is True


def test_patch_unknown_todo_is_404(client):
    assert client.patch("/api/todos/999", json={"done": True}).status_code == 404


def test_delete(client):
    todo = add(client)
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert client.get("/api/todos").json() == []
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 404


def test_todos_survive_a_restart(settings):
    add_user(settings, "maria")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        add(client, "still here")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        assert [todo["title"] for todo in client.get("/api/todos").json()] == ["still here"]


def test_page_and_its_files_are_served(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Taskly</title>")
    (static / "assets").mkdir()
    (static / "assets" / "index-abc123.js").write_text("export {};")
    (static / "assets" / "index-abc123.css").write_text("body {}")

    with TestClient(create_app(make_settings(tmp_path, static_dir=str(static)))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "<title>Taskly</title>" in page.text
        assert page.headers["cache-control"] == "no-cache"
        assert "cache-control" not in client.get("/assets/index-abc123.js").headers
        assert client.get("/assets/index-abc123.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/assets/index-abc123.css").headers["content-type"].startswith("text/css")


def test_api_runs_without_a_built_page(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404


def test_todos_record_who_added_and_who_ticked(app, client, settings):
    todo = add(client, "Buy milk")
    assert (todo["created_by"], todo["done_by"]) == ("maria", None)

    add_user(settings, "tom")
    with TestClient(app) as tom:
        login(tom, "tom")
        done = tom.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()
        assert (done["created_by"], done["done_by"]) == ("maria", "tom")
        renamed = tom.patch(f"/api/todos/{todo['id']}", json={"title": "Buy oat milk"}).json()
        assert renamed["done_by"] == "tom"

    undone = client.patch(f"/api/todos/{todo['id']}", json={"done": False}).json()
    assert undone["done_by"] is None


def test_todos_need_a_login(anon):
    assert anon.get("/api/todos").status_code == 401
    assert anon.post("/api/todos", json={"title": "x"}).status_code == 401


def test_api_docs_are_off_unless_asked_for(client, tmp_path):
    # With Caddy's password gone they would be public, and /docs loads its viewer from a CDN.
    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404
    with TestClient(create_app(make_settings(tmp_path / "local", api_docs=True))) as local:
        assert local.get("/docs").status_code == 200
        assert local.get("/openapi.json").status_code == 200
