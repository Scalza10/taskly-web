from contextlib import closing

import pytest

from taskly import admin, db, sessions, users
from conftest import PASSWORD, add_user


def answers(*replies):
    """A stand-in for getpass that answers in order."""
    replies = list(replies)
    return lambda _question: replies.pop(0)


def run(settings, *argv, prompt=answers()):
    return admin.main(list(argv), settings=settings, prompt=prompt)


def open_db(settings):
    return closing(db.connect(settings.db_path))


def test_add_user_with_a_typed_password(settings):
    assert run(settings, "add-user", "maria", prompt=answers(PASSWORD, PASSWORD)) == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is not None


def test_add_user_generates_a_password_when_left_empty(settings, capsys):
    assert run(settings, "add-user", "maria", prompt=answers("")) == 0
    printed = capsys.readouterr().out
    password = printed.strip().splitlines()[-1].split(": ", 1)[1]
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", password) is not None


def test_add_user_refuses_mismatched_passwords(settings, capsys):
    assert run(settings, "add-user", "maria", prompt=answers(PASSWORD, PASSWORD + "x")) == 1
    assert "don't match" in capsys.readouterr().err


def test_add_user_refuses_a_taken_name(settings, capsys):
    add_user(settings, "maria")
    assert run(settings, "add-user", "MARIA", prompt=answers(PASSWORD, PASSWORD)) == 1
    assert "already exists" in capsys.readouterr().err


def test_reset_password_logs_out_everywhere(settings):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        token = sessions.create_session(conn, maria["id"])
    assert run(settings, "reset-password", "maria", prompt=answers("a new password", "a new password")) == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", "a new password") is not None
        assert sessions.session_user(conn, token) is None


def test_disable_and_enable(settings):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        token = sessions.create_session(conn, maria["id"])
    assert run(settings, "disable-user", "maria") == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is None
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert run(settings, "enable-user", "maria") == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is not None
        assert sessions.session_user(conn, token) is None  # the old session stays gone


def test_revoke_sessions(settings, capsys):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        sessions.create_session(conn, maria["id"])
        sessions.create_session(conn, maria["id"])
    assert run(settings, "revoke-sessions", "maria") == 0
    assert "2 sessions ended" in capsys.readouterr().out


def test_list_users(settings, capsys):
    add_user(settings, "maria")
    add_user(settings, "tom")
    run(settings, "disable-user", "tom")
    capsys.readouterr()
    assert run(settings, "list-users") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[:4] == ["maria", "active", "0", "sessions"]
    assert lines[1].split()[:2] == ["tom", "disabled"]


@pytest.mark.parametrize("command", ["reset-password", "disable-user", "enable-user", "revoke-sessions"])
def test_unknown_users_are_an_error(settings, capsys, command):
    assert run(settings, command, "nobody", prompt=answers(PASSWORD, PASSWORD)) == 1
    assert "No user nobody" in capsys.readouterr().err
