import pytest

from taskly import users
from conftest import PASSWORD


def test_create_and_find_ignores_case(conn):
    maria = users.create_user(conn, "Maria", PASSWORD)
    assert maria["username"] == "Maria"
    assert maria["disabled_at"] is None
    assert users.find_user(conn, "maria")["id"] == maria["id"]


@pytest.mark.parametrize("name", ["m", "x" * 33, "has space", "émile", "a/b", ""])
def test_bad_usernames_are_refused(conn, name):
    with pytest.raises(users.UserError):
        users.create_user(conn, name, PASSWORD)


def test_names_are_unique_regardless_of_case(conn):
    users.create_user(conn, "maria", PASSWORD)
    with pytest.raises(users.UserError, match="already exists"):
        users.create_user(conn, "MARIA", PASSWORD)


def test_short_passwords_are_refused(conn):
    with pytest.raises(users.UserError, match="at least 6"):
        users.create_user(conn, "maria", "12345")


def test_authenticate(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    assert users.authenticate(conn, "MARIA", PASSWORD)["id"] == maria["id"]
    assert users.authenticate(conn, "maria", "wrong password!") is None
    assert users.authenticate(conn, "nobody", PASSWORD) is None


def test_disabled_users_cannot_authenticate(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    users.set_disabled(conn, maria["id"], True)
    assert users.authenticate(conn, "maria", PASSWORD) is None
    assert users.get_user(conn, maria["id"])["disabled_at"] is not None
    users.set_disabled(conn, maria["id"], False)
    assert users.authenticate(conn, "maria", PASSWORD) is not None


def test_set_password(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    users.set_password(conn, maria["id"], "a brand new one")
    assert users.authenticate(conn, "maria", "a brand new one") is not None
    assert users.authenticate(conn, "maria", PASSWORD) is None
    with pytest.raises(users.UserError):
        users.set_password(conn, maria["id"], "short")


def test_list_users_counts_sessions(conn):
    from taskly import sessions

    maria = users.create_user(conn, "maria", PASSWORD)
    users.create_user(conn, "ann", PASSWORD)
    sessions.create_session(conn, maria["id"])
    listed = users.list_users(conn)
    assert [(u["username"], u["sessions"]) for u in listed] == [("ann", 0), ("maria", 1)]


def test_an_unknown_name_still_checks_a_password(conn, monkeypatch):
    from taskly import passwords

    checked = []
    real = passwords.verify_password

    def recording(password, stored):
        checked.append(stored)
        return real(password, stored)

    monkeypatch.setattr(passwords, "verify_password", recording)
    assert users.authenticate(conn, "nobody", PASSWORD) is None
    assert checked == [passwords.DUMMY_HASH]
