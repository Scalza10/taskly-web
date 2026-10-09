import uuid

import pytest

from taskly import lists, snapshot, tasks, users
from conftest import PASSWORD


@pytest.fixture
def maria(conn):
    return users.create_user(conn, "maria", PASSWORD)


@pytest.fixture
def tom(conn):
    return users.create_user(conn, "tom", PASSWORD)


@pytest.fixture
def groceries(conn, maria):
    return lists.create_list(conn, "Groceries", maria["id"])


def new_id():
    return str(uuid.uuid4())


def test_create_returns_the_task_with_its_author(conn, maria, groceries):
    task_id = new_id()
    task, created = tasks.create_task(conn, task_id, groceries, "Milk", maria["id"])
    assert created is True
    assert task["id"] == task_id and task["list_id"] == groceries
    assert (task["title"], task["status"], task["done"], task["created_by"], task["done_by"]) == ("Milk", "new", False, "maria", None)
    assert task["created_at"].endswith("Z")


def test_creating_the_same_id_again_changes_nothing(conn, maria, groceries):
    task_id = new_id()
    tasks.create_task(conn, task_id, groceries, "Milk", maria["id"])
    task, created = tasks.create_task(conn, task_id, groceries, "Oat milk", maria["id"])
    assert created is False
    assert task["title"] == "Milk"
    assert len(tasks.list_tasks(conn, groceries)) == 1


def test_update_records_who_ticked(conn, maria, tom, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    done = tasks.update_task(conn, task["id"], tom["id"], done=True)
    assert (done["status"], done["done"], done["done_by"]) == ("done", True, "tom")
    renamed = tasks.update_task(conn, task["id"], maria["id"], title="Oat milk")
    assert (renamed["title"], renamed["done_by"]) == ("Oat milk", "tom")
    undone = tasks.update_task(conn, task["id"], maria["id"], done=False)
    assert (undone["status"], undone["done"], undone["done_by"]) == ("new", False, None)
    assert tasks.update_task(conn, new_id(), maria["id"], done=True) is None


def test_delete(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    assert tasks.delete_task(conn, task["id"]) is True
    assert tasks.delete_task(conn, task["id"]) is False


def test_status_moves_a_task_along(conn, maria, tom, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    started = tasks.update_task(conn, task["id"], tom["id"], status="progress")
    assert (started["status"], started["done"], started["done_by"]) == ("progress", False, None)
    finished = tasks.update_task(conn, task["id"], tom["id"], status="done")
    assert (finished["status"], finished["done"], finished["done_by"]) == ("done", True, "tom")
    back = tasks.update_task(conn, task["id"], maria["id"], status="progress")
    assert (back["status"], back["done_by"]) == ("progress", None)


def test_unticking_reopens_only_a_done_task(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    tasks.update_task(conn, task["id"], maria["id"], status="progress")
    # An older page (or an agent) that only knows done: an in-progress task isn't done already.
    assert tasks.update_task(conn, task["id"], maria["id"], done=False)["status"] == "progress"
    assert tasks.update_task(conn, task["id"], maria["id"], done=True)["status"] == "done"
    assert tasks.update_task(conn, task["id"], maria["id"], done=False)["status"] == "new"


def test_status_beats_done(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    assert tasks.update_task(conn, task["id"], maria["id"], done=True, status="progress")["status"] == "progress"


def test_tasks_sort_open_first_then_oldest(conn, maria, groceries):
    ids = {}
    for title in ["first", "second", "third", "fourth"]:
        ids[title] = tasks.create_task(conn, new_id(), groceries, title, maria["id"])[0]["id"]
    tasks.update_task(conn, ids["first"], maria["id"], done=True)
    tasks.update_task(conn, ids["third"], maria["id"], status="progress")
    # All four share a created_at second; insertion order breaks the tie.
    assert [t["title"] for t in tasks.list_tasks(conn, groceries)] == ["second", "third", "fourth", "first"]


def test_snapshot_has_only_my_lists_with_members_and_tasks(conn, maria, tom, groceries):
    lists.add_member(conn, groceries, tom["id"])
    lists.create_list(conn, "tom's own", tom["id"])
    lists.create_list(conn, "apples", maria["id"])
    tasks.create_task(conn, new_id(), groceries, "Milk", tom["id"])

    seen = snapshot.snapshot(conn, maria)
    assert seen["me"] == "maria"
    assert [l["name"] for l in seen["lists"]] == ["apples", "Groceries"]  # case-insensitive
    shared = seen["lists"][1]
    assert (shared["owner"], shared["role"], shared["members"]) == ("maria", "owner", ["maria", "tom"])
    assert [t["title"] for t in shared["tasks"]] == ["Milk"]
    assert snapshot.snapshot(conn, tom)["lists"][0]["role"] == "member"


def test_disabled_members_are_not_listed(conn, maria, tom, groceries):
    lists.add_member(conn, groceries, tom["id"])
    users.set_disabled(conn, tom["id"], True)
    assert snapshot.list_view(conn, groceries, maria["id"])["members"] == ["maria"]
