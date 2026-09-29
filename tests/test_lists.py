import pytest

from taskly import lists, users
from conftest import PASSWORD


@pytest.fixture
def people(conn):
    return {name: users.create_user(conn, name, PASSWORD)["id"] for name in ["maria", "tom", "ann", "zoe"]}


def test_the_creator_owns_the_list_and_is_a_member(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    assert lists.role(conn, list_id, people["maria"]) == "owner"
    assert lists.role(conn, list_id, people["tom"]) is None


def test_members(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    assert lists.add_member(conn, list_id, people["tom"]) is True
    assert lists.add_member(conn, list_id, people["tom"]) is False
    assert lists.role(conn, list_id, people["tom"]) == "member"
    assert lists.remove_member(conn, list_id, people["tom"]) is True
    assert lists.remove_member(conn, list_id, people["tom"]) is False
    assert lists.role(conn, list_id, people["tom"]) is None


def test_rename_and_delete(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    lists.rename_list(conn, list_id, "Food")
    assert conn.execute("SELECT name FROM lists WHERE id = ?", (list_id,)).fetchone()[0] == "Food"
    lists.delete_list(conn, list_id)
    assert lists.role(conn, list_id, people["maria"]) is None


def test_the_first_user_claims_unowned_lists(conn, people):
    conn.execute("INSERT INTO lists (id, name) VALUES ('legacy', 'Taskly')")
    conn.commit()
    assert lists.claim_unowned(conn, people["maria"]) == ["Taskly"]
    assert lists.role(conn, "legacy", people["maria"]) == "owner"
    assert lists.claim_unowned(conn, people["tom"]) == []


def test_hand_over_goes_to_the_earliest_active_member(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    for name in ["ann", "tom", "zoe"]:
        lists.add_member(conn, list_id, people[name])
    users.set_disabled(conn, people["ann"], True)  # joined first, but disabled

    assert lists.hand_over(conn, people["maria"]) == [("Groceries", "tom")]
    assert lists.role(conn, list_id, people["tom"]) == "owner"
    assert lists.role(conn, list_id, people["maria"]) == "member"


def test_hand_over_leaves_lists_nobody_else_is_in(conn, people):
    list_id = lists.create_list(conn, "Private", people["maria"])
    assert lists.hand_over(conn, people["maria"]) == []
    assert lists.role(conn, list_id, people["maria"]) == "owner"
