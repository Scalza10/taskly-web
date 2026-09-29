"""Login sessions: one row per logged-in device, found by the SHA-256 of the cookie's token.

A session lasts LIFETIME from its last use. last_used_at is written at most every TOUCH_EVERY,
and session_user says when it was, so the cookie's Max-Age can be renewed at the same time."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

LIFETIME = timedelta(days=90)
TOUCH_EVERY = timedelta(hours=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format(when: datetime) -> str:
    return when.strftime(TIME_FORMAT)


def _parse(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT).replace(tzinfo=timezone.utc)


def create_session(conn: sqlite3.Connection, user_id: int, device: str = "") -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        # Timestamps in TIME_FORMAT sort as text, so this compares correctly.
        conn.execute("DELETE FROM sessions WHERE last_used_at < ?", (_format(_now() - LIFETIME),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, device) VALUES (?, ?, ?)", (_hash(token), user_id, device)
        )
    return token


def session_user(conn: sqlite3.Connection, token: str) -> tuple[dict, bool] | None:
    """The active user behind a token, and whether the session was just touched. None if there is none."""
    row = conn.execute(
        """SELECT s.token_hash, s.last_used_at, u.id, u.username
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND u.disabled_at IS NULL""",
        (_hash(token),),
    ).fetchone()
    if row is None:
        return None
    now = _now()
    idle = now - _parse(row["last_used_at"])
    if idle > LIFETIME:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
        return None
    touched = idle >= TOUCH_EVERY
    if touched:
        with conn:
            conn.execute("UPDATE sessions SET last_used_at = ? WHERE token_hash = ?", (_format(now), row["token_hash"]))
    return {"id": row["id"], "username": row["username"]}, touched


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))


def delete_user_sessions(conn: sqlite3.Connection, user_id: int, keep_token: str | None = None) -> int:
    """Log a user out everywhere, except the session of keep_token. Returns how many ended."""
    keep = _hash(keep_token) if keep_token else ""
    with conn:
        cursor = conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep))
    return cursor.rowcount


_BROWSERS = [("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")]
_SYSTEMS = [("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
            ("Macintosh", "Mac"), ("Linux", "Linux")]


def device_label(user_agent: str) -> str:
    """A short name for a browser, to tell sessions apart: "Chrome on Android". Empty if unknown."""
    browser = next((name for mark, name in _BROWSERS if mark in user_agent), None)
    system = next((name for mark, name in _SYSTEMS if mark in user_agent), None)
    return f"{browser} on {system}" if browser and system else ""
