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
    assert (task["id"], task["list_id"], task["title"], task["status"], task["done"]) == (task_id, made["id"], "Milk", "new", False)
    assert (task["created_by"], task["done_by"]) == ("maria", None)


def test_due_dates(client):
    made = new_list(client)
    response = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Milk", "due_date": "2026-10-17"})
    assert response.status_code == 201
    task = response.json()
    assert task["due_date"] == "2026-10-17"
    path = f"/api/tasks/{task['id']}"
    # A page from before due dates leaves it alone.
    assert client.patch(path, json={"status": "progress"}).json()["due_date"] == "2026-10-17"
    assert client.patch(path, json={"due_date": "2026-11-01"}).json()["due_date"] == "2026-11-01"
    assert client.patch(path, json={"due_date": None}).json()["due_date"] is None
    assert sync(client)["lists"][0]["tasks"][0]["due_date"] is None
    assert new_task(client, made["id"], "Eggs")["due_date"] is None


def test_a_due_date_is_only_a_calendar_day(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    path = f"/api/tasks/{task['id']}"
    for wrong in ["2026-02-30", "2026-10-17T09:00:00Z", "17/10/2026", "2026-1-7", "", 1760659200]:
        assert client.patch(path, json={"due_date": wrong}).status_code == 422, wrong
        created = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x", "due_date": wrong})
        assert created.status_code == 422, wrong
    assert client.get("/api/sync").json()["lists"][0]["tasks"][0]["due_date"] is None


def test_due_times(client):
    made = new_list(client)
    body = {"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Dentist",
            "due_date": "2026-10-18", "due_time": "15:00", "due_zone": "America/New_York"}
    task = client.post("/api/tasks", json=body).json()
    assert (task["due_date"], task["due_time"], task["due_zone"]) == ("2026-10-18", "15:00", "America/New_York")
    path = f"/api/tasks/{task['id']}"
    assert client.patch(path, json={"title": "Dentist (Dr Lee)"}).json()["due_time"] == "15:00"  # left alone
    moved = client.patch(path, json={"due_date": "2026-10-19", "due_time": "09:30", "due_zone": "Atlantic/Canary"}).json()
    assert (moved["due_date"], moved["due_time"], moved["due_zone"]) == ("2026-10-19", "09:30", "Atlantic/Canary")
    untimed = client.patch(path, json={"due_date": "2026-10-19"}).json()
    assert (untimed["due_date"], untimed["due_time"], untimed["due_zone"]) == ("2026-10-19", None, None)
    assert new_task(client, made["id"], "Eggs")["due_time"] is None


def test_a_due_time_needs_its_date_and_zone(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    path = f"/api/tasks/{task['id']}"
    day, zone = "2026-10-18", "America/New_York"
    for wrong in [
        {"due_date": day, "due_time": "15:00"},  # no zone
        {"due_date": day, "due_zone": zone},  # a zone, no time
        {"due_time": "15:00", "due_zone": zone},  # no date in the body
        {"due_time": None},
        {"due_date": None, "due_time": "15:00", "due_zone": zone},
        {"due_date": day, "due_time": "24:00", "due_zone": zone},
        {"due_date": day, "due_time": "3pm", "due_zone": zone},
        {"due_date": day, "due_time": "15:00:00", "due_zone": zone},
        {"due_date": day, "due_time": "15:00", "due_zone": "Mars/Olympus"},
        {"due_date": day, "due_time": "15:00", "due_zone": "America"},
        {"due_date": day, "due_time": "15:00", "due_zone": "../etc/passwd"},
        {"due_date": day, "due_time": "15:00", "due_zone": "EST" * 30},
    ]:
        assert client.patch(path, json=wrong).status_code == 422, wrong
        created = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x", **wrong})
        assert created.status_code == 422, wrong
    [stored] = client.get("/api/sync").json()["lists"][0]["tasks"]
    assert (stored["due_date"], stored["due_time"], stored["due_zone"]) == (None, None, None)


def test_notes(client):
    made = new_list(client)
    body = {"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Plumber", "notes": "  Call first\nhttps://example.com/leak  "}
    response = client.post("/api/tasks", json=body)
    assert response.status_code == 201
    task = response.json()
    assert task["notes"] == "Call first\nhttps://example.com/leak"  # trimmed, the line break kept
    path = f"/api/tasks/{task['id']}"
    # A page from before notes leaves them alone, whatever it changes.
    for change in [{"status": "progress"}, {"done": True}, {"done": False}, {"title": "Plumber (sink)"},
                   {"due_date": "2026-10-20"}, {"due_date": None}]:
        assert client.patch(path, json=change).json()["notes"] == "Call first\nhttps://example.com/leak", change
    assert client.patch(path, json={"notes": "Ask for Sam"}).json()["notes"] == "Ask for Sam"
    assert client.patch(path, json={"notes": "   "}).json()["notes"] is None
    client.patch(path, json={"notes": "again"})
    assert client.patch(path, json={"notes": None}).json()["notes"] is None
    client.patch(path, json={"notes": "in the sync"})
    assert sync(client)["lists"][0]["tasks"][0]["notes"] == "in the sync"
    assert new_task(client, made["id"], "Eggs")["notes"] is None


def test_notes_are_checked(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    path = f"/api/tasks/{task['id']}"
    for wrong in ["x" * 2001, 7, ["a"]]:
        assert client.patch(path, json={"notes": wrong}).status_code == 422, wrong
        created = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x", "notes": wrong})
        assert created.status_code == 422, wrong
    assert client.patch(path, json={"notes": "x" * 2000}).status_code == 200
    lone = client.patch(path, content='{"notes": "\\ud800"}', headers={"Content-Type": "application/json"})
    assert lone.status_code == 422


def test_repeats(client):
    made = new_list(client)
    body = {"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Bins", "due_date": "2026-10-19", "repeat": " freq=weekly "}
    response = client.post("/api/tasks", json=body)
    assert response.status_code == 201
    assert response.json()["repeat"] == "FREQ=WEEKLY;BYDAY=MO"  # canonical, its weekday from the due date
    path = f"/api/tasks/{body['id']}"
    # A page from before repeats leaves it alone; moving the date takes it along.
    for change in [{"title": "Bins out"}, {"notes": "Both"}, {"status": "progress"}, {"done": False}, {"status": "new"}]:
        assert client.patch(path, json=change).json()["repeat"] == "FREQ=WEEKLY;BYDAY=MO", change
    assert client.patch(path, json={"due_date": "2026-10-20"}).json()["repeat"] == "FREQ=WEEKLY;BYDAY=TU"
    assert client.patch(path, json={"repeat": "FREQ=WEEKLY;BYDAY=TH,MO"}).json()["repeat"] == "FREQ=WEEKLY;BYDAY=MO,TH"
    assert client.patch(path, json={"repeat": ""}).json()["repeat"] is None
    for stop in [{"repeat": None}, {"due_date": None}]:
        client.patch(path, json={"due_date": "2026-10-19", "repeat": "FREQ=DAILY"})
        assert client.patch(path, json=stop).json()["repeat"] is None, stop
    client.patch(path, json={"due_date": "2026-10-19", "repeat": "FREQ=DAILY;INTERVAL=3;FROM=DONE"})
    assert sync(client)["lists"][0]["tasks"][0]["repeat"] == "FREQ=DAILY;INTERVAL=3;FROM=DONE"
    assert new_task(client, made["id"], "Eggs")["repeat"] is None


def test_finishing_a_repeating_task_makes_the_next(client):
    made = new_list(client)
    body = {"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Bins", "due_date": "2026-10-19", "repeat": "FREQ=WEEKLY"}
    client.post("/api/tasks", json=body)
    next_id = str(uuid.uuid4())
    finish = {"status": "done", "next_id": next_id, "finished_on": "2026-10-21"}

    done = client.patch(f"/api/tasks/{body['id']}", json=finish)

    assert done.status_code == 200
    assert (done.json()["status"], done.json()["repeat"]) == ("done", None)
    assert client.patch(f"/api/tasks/{body['id']}", json=finish).status_code == 200  # a retry makes nothing more
    found = [(t["id"], t["status"], t["due_date"], t["repeat"]) for t in sync(client)["lists"][0]["tasks"]]
    assert found == [(next_id, "new", "2026-10-26", "FREQ=WEEKLY;BYDAY=MO"), (body["id"], "done", "2026-10-19", None)]


def test_a_page_from_before_repeats_finishing_one_makes_the_next(client):
    from taskly import repeats

    for change in [{"done": True}, {"status": "done"}]:
        made = new_list(client, str(change))
        body = {"id": str(uuid.uuid4()), "list_id": made["id"], "title": "Plants", "due_date": "2020-01-06", "repeat": "FREQ=DAILY"}
        client.post("/api/tasks", json=body)
        assert client.patch(f"/api/tasks/{body['id']}", json=change).status_code == 200
        found = next(each for each in sync(client)["lists"] if each["id"] == made["id"])["tasks"]
        assert [(t["status"], t["due_date"], t["repeat"]) for t in found] == [
            ("new", repeats.today_for(None), "FREQ=DAILY"), ("done", "2020-01-06", None)], change


def test_repeats_are_checked(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    path = f"/api/tasks/{task['id']}"
    client.patch(path, json={"due_date": "2026-10-19"})
    for wrong in ["FREQ=HOURLY", "FREQ=WEEKLY;BYDAY=XX", "FREQ=DAILY;" + "x" * 200, 7, ["FREQ=DAILY"]]:
        assert client.patch(path, json={"repeat": wrong}).status_code == 422, wrong
        created = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x",
                                                  "due_date": "2026-10-19", "repeat": wrong})
        assert created.status_code == 422, wrong
    lone = client.patch(path, content='{"repeat": "FREQ=DAILY\\ud800"}', headers={"Content-Type": "application/json"})
    assert lone.status_code == 422
    # A repeat needs a due date: in the body, or already on the task.
    no_date = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x", "repeat": "FREQ=DAILY"})
    assert no_date.status_code == 422
    assert client.patch(path, json={"due_date": None, "repeat": "FREQ=DAILY"}).status_code == 422
    undated = new_task(client, made["id"], "Eggs")
    refused = client.patch(f"/api/tasks/{undated['id']}", json={"repeat": "FREQ=DAILY"})
    assert (refused.status_code, refused.json()["detail"]) == (422, "A repeat needs a due date")
    # What finishing one sends.
    client.patch(path, json={"due_date": "2026-10-19", "repeat": "FREQ=DAILY"})
    for wrong in [{"next_id": "7"}, {"finished_on": "2026-02-30"}, {"finished_on": "today"}]:
        assert client.patch(path, json={"status": "done", **wrong}).status_code == 422, wrong
    clash = client.patch(path, json={"status": "done", "next_id": undated["id"]})
    assert (clash.status_code, clash.json()["detail"]) == (409, "That task id is already used")
    still = next(t for t in sync(client)["lists"][0]["tasks"] if t["id"] == task["id"])
    assert (still["status"], still["repeat"]) == ("new", "FREQ=DAILY")


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


def test_status_changes(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    path = f"/api/tasks/{task['id']}"
    started = client.patch(path, json={"status": "progress"}).json()
    assert (started["status"], started["done"], started["done_by"]) == ("progress", False, None)
    assert client.patch(path, json={"done": False}).json()["status"] == "progress"  # an older page unticking
    finished = client.patch(path, json={"status": "done"}).json()
    assert (finished["status"], finished["done"], finished["done_by"]) == ("done", True, "maria")
    assert client.patch(path, json={"done": False}).json()["status"] == "new"
    assert client.patch(path, json={"done": True, "status": "progress"}).json()["status"] == "progress"
    assert client.patch(path, json={"status": "later"}).status_code == 422
    assert client.patch(path, json={"status": None}).json()["status"] == "progress"


def test_sync_sorts_lists_by_name_and_tasks_open_first(client):
    new_list(client, "zoo")
    food = new_list(client, "Food")
    first = new_task(client, food["id"], "first")
    second = new_task(client, food["id"], "second")
    new_task(client, food["id"], "third")
    client.patch(f"/api/tasks/{first['id']}", json={"done": True})
    client.patch(f"/api/tasks/{second['id']}", json={"status": "progress"})
    seen = sync(client)
    assert [l["name"] for l in seen["lists"]] == ["Food", "zoo"]
    assert [t["title"] for t in seen["lists"][0]["tasks"]] == ["second", "third", "first"]


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
