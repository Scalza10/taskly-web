from fastapi.testclient import TestClient

from taskly.main import create_app


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
    with TestClient(create_app(settings)) as client:
        add(client, "still here")
    with TestClient(create_app(settings)) as client:
        assert [todo["title"] for todo in client.get("/api/todos").json()] == ["still here"]


def test_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "<title>Taskly</title>" in page.text
    assert client.get("/app.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/style.css").headers["content-type"].startswith("text/css")
