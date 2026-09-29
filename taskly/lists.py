"""Queries on lists and their members. The owner always has a member row too, so
"which lists can I see" is one lookup in list_members."""

import sqlite3
import uuid

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def role(conn: sqlite3.Connection, list_id: str, user_id: int) -> str | None:
    row = conn.execute(
        """SELECT l.owner_id FROM list_members m JOIN lists l ON l.id = m.list_id
           WHERE m.list_id = ? AND m.user_id = ?""",
        (list_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return "owner" if row["owner_id"] == user_id else "member"


def create_list(conn: sqlite3.Connection, name: str, owner_id: int) -> str:
    list_id = str(uuid.uuid4())
    with conn:
        conn.execute("INSERT INTO lists (id, name, owner_id) VALUES (?, ?, ?)", (list_id, name, owner_id))
        conn.execute("INSERT INTO list_members (list_id, user_id) VALUES (?, ?)", (list_id, owner_id))
    return list_id


def rename_list(conn: sqlite3.Connection, list_id: str, name: str) -> None:
    with conn:
        conn.execute(f"UPDATE lists SET name = ?, updated_at = {NOW} WHERE id = ?", (name, list_id))


def delete_list(conn: sqlite3.Connection, list_id: str) -> None:
    """Its tasks and member rows go with it (ON DELETE CASCADE)."""
    with conn:
        conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))


def add_member(conn: sqlite3.Connection, list_id: str, user_id: int) -> bool:
    with conn:
        cursor = conn.execute("INSERT OR IGNORE INTO list_members (list_id, user_id) VALUES (?, ?)", (list_id, user_id))
    return cursor.rowcount == 1


def remove_member(conn: sqlite3.Connection, list_id: str, user_id: int) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM list_members WHERE list_id = ? AND user_id = ?", (list_id, user_id))
    return cursor.rowcount == 1


def claim_unowned(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Lists without an owner (the old list, migrated before anyone had an account) go to this user."""
    names = [row[0] for row in conn.execute("SELECT name FROM lists WHERE owner_id IS NULL ORDER BY name")]
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO list_members (list_id, user_id) SELECT id, ? FROM lists WHERE owner_id IS NULL",
            (user_id,),
        )
        conn.execute("UPDATE lists SET owner_id = ? WHERE owner_id IS NULL", (user_id,))
    return names


def hand_over(conn: sqlite3.Connection, user_id: int) -> list[tuple[str, str]]:
    """Before disabling a user: each list they own passes to the active member who joined earliest."""
    moved = []
    for owned in conn.execute("SELECT id, name FROM lists WHERE owner_id = ? ORDER BY name", (user_id,)).fetchall():
        heir = conn.execute(
            """SELECT u.id, u.username FROM list_members m JOIN users u ON u.id = m.user_id
               WHERE m.list_id = ? AND m.user_id != ? AND u.disabled_at IS NULL
               ORDER BY m.joined_at, m.rowid LIMIT 1""",
            (owned["id"], user_id),
        ).fetchone()
        if heir:
            with conn:
                conn.execute(f"UPDATE lists SET owner_id = ?, updated_at = {NOW} WHERE id = ?", (heir["id"], owned["id"]))
            moved.append((owned["name"], heir["username"]))
    return moved
