import uuid

import pytest

from taskly import lists, repeats, snapshot, tasks, users
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
    assert task["due_date"] is None
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


def test_a_due_date_is_set_kept_and_removed(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"], "2026-10-17")
    assert task["due_date"] == "2026-10-17"
    # Other changes leave it alone.
    assert tasks.update_task(conn, task["id"], maria["id"], title="Oat milk", status="progress")["due_date"] == "2026-10-17"
    assert tasks.update_task(conn, task["id"], maria["id"], due_date="2026-10-20")["due_date"] == "2026-10-20"
    cleared = tasks.update_task(conn, task["id"], maria["id"], due_date=None)
    assert (cleared["due_date"], cleared["title"], cleared["status"]) == (None, "Oat milk", "progress")


def test_a_due_time_goes_with_its_date(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Dentist", maria["id"], "2026-10-18", "15:00", "America/New_York")
    assert (task["due_date"], task["due_time"], task["due_zone"]) == ("2026-10-18", "15:00", "America/New_York")
    assert tasks.update_task(conn, task["id"], maria["id"], status="progress")["due_time"] == "15:00"
    # A new date without a time is a date without a time.
    moved = tasks.update_task(conn, task["id"], maria["id"], due_date="2026-10-19")
    assert (moved["due_date"], moved["due_time"], moved["due_zone"]) == ("2026-10-19", None, None)
    timed = tasks.update_task(conn, task["id"], maria["id"], due_date="2026-10-20", due_time="09:30", due_zone="Atlantic/Canary")
    assert (timed["due_time"], timed["due_zone"]) == ("09:30", "Atlantic/Canary")
    cleared = tasks.update_task(conn, task["id"], maria["id"], due_date=None)
    assert (cleared["due_date"], cleared["due_time"], cleared["due_zone"]) == (None, None, None)


def test_notes_are_set_kept_and_removed(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"], notes="The oat one\nhttps://example.com")
    assert task["notes"] == "The oat one\nhttps://example.com"
    # Other changes leave them alone.
    kept = tasks.update_task(conn, task["id"], maria["id"], title="Oat milk", status="progress", due_date="2026-10-20")
    assert kept["notes"] == "The oat one\nhttps://example.com"
    assert tasks.update_task(conn, task["id"], maria["id"], notes="Two cartons")["notes"] == "Two cartons"
    assert tasks.update_task(conn, task["id"], maria["id"], notes="")["notes"] is None
    tasks.update_task(conn, task["id"], maria["id"], notes="again")
    cleared = tasks.update_task(conn, task["id"], maria["id"], notes=None)
    assert (cleared["notes"], cleared["title"], cleared["due_date"]) == (None, "Oat milk", "2026-10-20")
    assert tasks.create_task(conn, new_id(), groceries, "Eggs", maria["id"], notes="")[0]["notes"] is None
    assert tasks.create_task(conn, new_id(), groceries, "Bread", maria["id"])[0]["notes"] is None


def test_finishing_a_repeating_task_makes_the_next(conn, maria, tom, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Bins", maria["id"], "2026-10-19", "07:30", "Europe/Madrid",
                                notes="Both of them", repeat="FREQ=WEEKLY")
    assert task["repeat"] == "FREQ=WEEKLY;BYDAY=MO"  # its weekday, from the due date
    tasks.update_task(conn, task["id"], tom["id"], status="progress")
    next_id = new_id()

    done = tasks.update_task(conn, task["id"], tom["id"], status="done", next_id=next_id, finished_on="2026-10-21")

    assert (done["status"], done["done_by"], done["repeat"]) == ("done", "tom", None)  # the repeat moved on
    made = tasks.get_task(conn, next_id)
    fields = ("list_id", "title", "notes", "status", "due_date", "due_time", "due_zone", "repeat", "created_by", "done_by")
    assert {key: made[key] for key in fields} == {
        "list_id": groceries, "title": "Bins", "notes": "Both of them", "status": "new", "due_date": "2026-10-26",
        "due_time": "07:30", "due_zone": "Europe/Madrid", "repeat": "FREQ=WEEKLY;BYDAY=MO", "created_by": "maria",
        "done_by": None,
    }
    # Finishing it again (a retry, another device) makes nothing; nor does unticking and finishing
    # it again: the next one repeats now, and both stay.
    tasks.update_task(conn, task["id"], tom["id"], status="done", next_id=new_id())
    reopened = tasks.update_task(conn, task["id"], tom["id"], done=False)
    assert (reopened["status"], reopened["repeat"]) == ("new", None)
    tasks.update_task(conn, task["id"], tom["id"], done=True, next_id=new_id())
    assert len(tasks.list_tasks(conn, groceries)) == 2
    # The next one makes its own.
    third = new_id()
    tasks.update_task(conn, next_id, maria["id"], done=True, next_id=third, finished_on="2026-10-26")
    assert (tasks.get_task(conn, third)["due_date"], tasks.get_task(conn, next_id)["repeat"]) == ("2026-11-02", None)


def test_finished_without_a_day_or_an_id_the_server_picks_them(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Water the plants", maria["id"], "2020-01-06", repeat="FREQ=DAILY")
    tasks.update_task(conn, task["id"], maria["id"], done=True)  # an agent, or a page from before repeats
    made = [t for t in tasks.list_tasks(conn, groceries) if t["id"] != task["id"]]
    assert [(t["status"], t["due_date"], t["repeat"]) for t in made] == [("new", repeats.today_for(None), "FREQ=DAILY")]
    assert str(uuid.UUID(made[0]["id"])) == made[0]["id"]


def test_a_repeat_needs_a_due_date(conn, maria, groceries):
    with pytest.raises(tasks.NoDueDate):
        tasks.create_task(conn, new_id(), groceries, "Bins", maria["id"], repeat="FREQ=DAILY")
    task, _ = tasks.create_task(conn, new_id(), groceries, "Bins", maria["id"])
    with pytest.raises(tasks.NoDueDate):
        tasks.update_task(conn, task["id"], maria["id"], repeat="FREQ=DAILY")
    with pytest.raises(tasks.NoDueDate):
        tasks.update_task(conn, task["id"], maria["id"], due_date=None, repeat="FREQ=DAILY")
    assert tasks.get_task(conn, task["id"])["repeat"] is None
    # With the date in the same change, or one set before: anchored on it.
    monthly = tasks.update_task(conn, task["id"], maria["id"], due_date="2026-10-19", repeat="FREQ=MONTHLY")
    assert monthly["repeat"] == "FREQ=MONTHLY;BYMONTHDAY=19"
    # Moving the date takes a repeat set from it along; other changes leave it.
    assert tasks.update_task(conn, task["id"], maria["id"], due_date="2026-10-31")["repeat"] == "FREQ=MONTHLY;BYMONTHDAY=31"
    others = tasks.update_task(conn, task["id"], maria["id"], title="Bins out", notes="x", status="progress")
    assert others["repeat"] == "FREQ=MONTHLY;BYMONTHDAY=31"
    assert tasks.update_task(conn, task["id"], maria["id"], repeat="FREQ=WEEKLY;BYDAY=MO,TH")["repeat"] == "FREQ=WEEKLY;BYDAY=MO,TH"
    # Removed: with "" or None, or with the due date.
    assert tasks.update_task(conn, task["id"], maria["id"], repeat="")["repeat"] is None
    tasks.update_task(conn, task["id"], maria["id"], repeat="FREQ=DAILY")
    assert tasks.update_task(conn, task["id"], maria["id"], repeat=None)["repeat"] is None
    tasks.update_task(conn, task["id"], maria["id"], repeat="FREQ=DAILY")
    assert tasks.update_task(conn, task["id"], maria["id"], due_date=None)["repeat"] is None


def test_a_next_id_thats_taken_changes_nothing(conn, maria, groceries):
    milk, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    task, _ = tasks.create_task(conn, new_id(), groceries, "Bins", maria["id"], "2026-10-19", repeat="FREQ=DAILY")
    with pytest.raises(tasks.IdTaken):
        tasks.update_task(conn, task["id"], maria["id"], status="done", next_id=milk["id"])
    after = tasks.get_task(conn, task["id"])
    assert (after["status"], after["repeat"]) == ("new", "FREQ=DAILY")
    assert len(tasks.list_tasks(conn, groceries)) == 2


def test_after_the_last_day_there_is_the_repeat_ends(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Bins", maria["id"], "9999-12-31", repeat="FREQ=DAILY")
    done = tasks.update_task(conn, task["id"], maria["id"], done=True, next_id=new_id(), finished_on="9999-12-31")
    assert (done["status"], done["repeat"]) == ("done", None)
    assert len(tasks.list_tasks(conn, groceries)) == 1


def test_delete_done_deletes_only_that_lists_finished_tasks(conn, maria, groceries):
    other = lists.create_list(conn, "Chores", maria["id"])
    ids = {}
    for list_id, title in [(groceries, "Milk"), (groceries, "Eggs"), (groceries, "Bread"), (other, "Sweep")]:
        ids[title] = tasks.create_task(conn, new_id(), list_id, title, maria["id"])[0]["id"]
    for title in ["Milk", "Eggs", "Sweep"]:
        tasks.update_task(conn, ids[title], maria["id"], status="done")

    deleted = tasks.delete_done(conn, groceries)
    assert sorted(t["title"] for t in deleted) == ["Eggs", "Milk"]
    assert all(t["done"] and t["done_by"] == "maria" for t in deleted)
    assert [t["title"] for t in tasks.list_tasks(conn, groceries)] == ["Bread"]
    assert [t["title"] for t in tasks.list_tasks(conn, other)] == ["Sweep"]
    assert tasks.delete_done(conn, groceries) == []


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


def test_tasks_with_a_due_date_come_first_soonest_first(conn, maria, groceries):
    def add(title, due_date=None, due_time=None, due_zone=None, status=None):
        task, _ = tasks.create_task(conn, new_id(), groceries, title, maria["id"], due_date, due_time, due_zone)
        if status:
            tasks.update_task(conn, task["id"], maria["id"], status=status)
    add("undated, oldest")
    add("Oct 20", "2026-10-20")
    add("Oct 18, 3 pm in Florida", "2026-10-18", "15:00", "America/New_York")  # 19:00 UTC
    add("Oct 18, 6 pm in La Palma", "2026-10-18", "18:00", "Atlantic/Canary")  # 17:00 UTC: sooner
    add("Oct 18, the day", "2026-10-18")  # the end of the day: after that day's times
    add("Oct 17, done", "2026-10-17", status="done")
    add("undated, newer")
    add("Oct 19", "2026-10-19")
    add("undated, done", status="done")
    assert [t["title"] for t in tasks.list_tasks(conn, groceries)] == [
        "Oct 18, 6 pm in La Palma", "Oct 18, 3 pm in Florida", "Oct 18, the day", "Oct 19", "Oct 20",
        "undated, oldest", "undated, newer",
        "Oct 17, done", "undated, done",
    ]


def test_the_latest_day_still_sorts(conn, maria, groceries):
    tasks.create_task(conn, new_id(), groceries, "far", maria["id"], "9999-12-31")
    tasks.create_task(conn, new_id(), groceries, "near", maria["id"], "0001-01-01", "00:00", "Asia/Tokyo")
    assert [t["title"] for t in tasks.list_tasks(conn, groceries)] == ["near", "far"]


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
