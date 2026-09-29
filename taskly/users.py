"""Queries on users. Usernames are case-insensitive (COLLATE NOCASE). Users are disabled, never deleted."""

import re
import sqlite3

from . import passwords

USERNAME = re.compile(r"[A-Za-z0-9._-]{2,32}")
COLUMNS = "id, username, created_at, disabled_at"


class UserError(ValueError):
    """A username or password that can't be used. The message is shown to people as is."""


def check_username(name: str) -> None:
    if not USERNAME.fullmatch(name):
        raise UserError("Usernames are 2-32 letters, digits, '.', '_' or '-'")


def check_password(password: str) -> None:
    if len(password) < passwords.MIN_LENGTH:
        raise UserError(f"Passwords need at least {passwords.MIN_LENGTH} characters")


def create_user(conn: sqlite3.Connection, username: str, password: str) -> dict:
    check_username(username)
    check_password(password)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, passwords.hash_password(password)),
            )
    except sqlite3.IntegrityError:
        raise UserError(f"{username} already exists") from None
    return get_user(conn, cursor.lastrowid)


def get_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def find_user(conn: sqlite3.Connection, username: str) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict | None:
    """The active user with this name and password, or None."""
    row = conn.execute(
        "SELECT id, password_hash, disabled_at FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        passwords.verify_password(password, passwords.DUMMY_HASH)
        return None
    if not passwords.verify_password(password, row["password_hash"]) or row["disabled_at"]:
        return None
    return get_user(conn, row["id"])


def set_password(conn: sqlite3.Connection, user_id: int, password: str) -> None:
    check_password(password)
    with conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (passwords.hash_password(password), user_id))


def set_disabled(conn: sqlite3.Connection, user_id: int, disabled: bool) -> None:
    with conn:
        conn.execute(
            "UPDATE users SET disabled_at = CASE WHEN ? THEN strftime('%Y-%m-%dT%H:%M:%SZ', 'now') END WHERE id = ?",
            (disabled, user_id),
        )


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT u.id, u.username, u.created_at, u.disabled_at,
                  (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id) AS sessions
           FROM users u ORDER BY u.username"""
    ).fetchall()
    return [dict(row) for row in rows]
