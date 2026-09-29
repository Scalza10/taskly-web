from datetime import datetime, timedelta, timezone

import pytest

from taskly import sessions, users
from conftest import PASSWORD


@pytest.fixture
def maria(conn):
    return users.create_user(conn, "maria", PASSWORD)


def age(conn, token, delta):
    """Pretend the session was last used `delta` ago."""
    when = (datetime.now(timezone.utc) - delta).strftime(sessions.TIME_FORMAT)
    conn.execute("UPDATE sessions SET last_used_at = ? WHERE token_hash = ?", (when, sessions._hash(token)))
    conn.commit()


def test_a_new_session_finds_its_user(conn, maria):
    token = sessions.create_session(conn, maria["id"], "Firefox on Windows")
    user, touched = sessions.session_user(conn, token)
    assert user == {"id": maria["id"], "username": "maria"}
    assert touched is False


def test_only_the_hash_is_stored(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored != token
    assert len(stored) == 64


def test_unknown_tokens_find_nobody(conn, maria):
    sessions.create_session(conn, maria["id"])
    assert sessions.session_user(conn, "made-up") is None


def test_use_after_an_hour_touches_the_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    age(conn, token, timedelta(hours=2))
    assert sessions.session_user(conn, token)[1] is True
    assert sessions.session_user(conn, token)[1] is False  # just touched


def test_sessions_expire_90_days_after_last_use(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    age(conn, token, timedelta(days=89))
    assert sessions.session_user(conn, token) is not None
    age(conn, token, timedelta(days=91))
    assert sessions.session_user(conn, token) is None
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_a_new_login_cleans_up_expired_sessions(conn, maria):
    old = sessions.create_session(conn, maria["id"])
    age(conn, old, timedelta(days=100))
    sessions.create_session(conn, maria["id"])
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_disabled_users_have_no_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    users.set_disabled(conn, maria["id"], True)
    assert sessions.session_user(conn, token) is None


def test_delete_user_sessions_can_keep_one(conn, maria):
    keep = sessions.create_session(conn, maria["id"])
    gone = sessions.create_session(conn, maria["id"])
    assert sessions.delete_user_sessions(conn, maria["id"], keep_token=keep) == 1
    assert sessions.session_user(conn, keep) is not None
    assert sessions.session_user(conn, gone) is None


def test_delete_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    sessions.delete_session(conn, token)
    assert sessions.session_user(conn, token) is None


@pytest.mark.parametrize("agent, label", [
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36", "Chrome on Android"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1", "Safari on iPhone"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36 Edg/129.0", "Edge on Windows"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox on Mac"),
    ("curl/8.9.1", ""),
])
def test_device_label(agent, label):
    assert sessions.device_label(agent) == label
