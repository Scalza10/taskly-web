"""Queries on tasks. IDs are UUIDs made by the device, so creating is safe to retry.
Every function takes an open connection and returns plain dicts (done as a bool, people by name)."""

import sqlite3

SELECT = """SELECT t.id, t.list_id, t.title, t.done, c.username AS created_by, d.username AS done_by,
                   t.created_at, t.updated_at
            FROM tasks t
            LEFT JOIN users c ON c.id = t.created_by
            LEFT JOIN users d ON d.id = t.done_by"""


def _to_dict(row: sqlite3.Row) -> dict:
    task = dict(row)
    task["done"] = bool(task["done"])
    return task


def get_task(conn: sqlite3.Connection, task_id: str) -> dict | None:
    row = conn.execute(f"{SELECT} WHERE t.id = ?", (task_id,)).fetchone()
    return _to_dict(row) if row else None


def list_tasks(conn: sqlite3.Connection, list_id: str) -> list[dict]:
    # Open ones first, then newest first; rowid breaks ties within the same second.
    rows = conn.execute(f"{SELECT} WHERE t.list_id = ? ORDER BY t.done, t.created_at DESC, t.rowid DESC", (list_id,))
    return [_to_dict(row) for row in rows]


def create_task(conn: sqlite3.Connection, task_id: str, list_id: str, title: str, user_id: int) -> tuple[dict, bool]:
    """(task, created). If the id exists already (a device retrying), the stored task, unchanged."""
    try:
        with conn:
            conn.execute(
                "INSERT INTO tasks (id, list_id, title, created_by) VALUES (?, ?, ?, ?)",
                (task_id, list_id, title, user_id),
            )
    except sqlite3.IntegrityError:
        existing = get_task(conn, task_id)
        if existing is None:  # not a duplicate id: the list vanished meanwhile
            raise
        return existing, False
    return get_task(conn, task_id), True


def update_task(conn: sqlite3.Connection, task_id: str, user_id: int, *, title: str | None = None,
                done: bool | None = None) -> dict | None:
    """Changes only the fields given; ticking records who did it. None if there is no such task."""
    changes = {}
    if title is not None:
        changes["title"] = title
    if done is not None:
        changes["done"] = int(done)
        changes["done_by"] = user_id if done else None
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with conn:
            conn.execute(
                f"UPDATE tasks SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (*changes.values(), task_id),
            )
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0
