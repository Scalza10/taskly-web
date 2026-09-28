"""Queries on the todos table. Every function takes an open connection and returns plain dicts."""

import sqlite3

COLUMNS = "id, title, done, created_at, updated_at"


def _to_dict(row: sqlite3.Row) -> dict:
    todo = dict(row)
    todo["done"] = bool(todo["done"])
    return todo


def list_todos(conn: sqlite3.Connection) -> list[dict]:
    # Open ones first, then newest first.
    rows = conn.execute(f"SELECT {COLUMNS} FROM todos ORDER BY done, id DESC").fetchall()
    return [_to_dict(row) for row in rows]


def get_todo(conn: sqlite3.Connection, todo_id: int) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM todos WHERE id = ?", (todo_id,)).fetchone()
    return _to_dict(row) if row else None


def create_todo(conn: sqlite3.Connection, title: str) -> dict:
    with conn:
        cursor = conn.execute("INSERT INTO todos (title) VALUES (?)", (title,))
    return get_todo(conn, cursor.lastrowid)


def update_todo(conn: sqlite3.Connection, todo_id: int, *, title: str | None = None,
                done: bool | None = None) -> dict | None:
    """Changes only the fields given. None if there is no such todo."""
    changes = {}
    if title is not None:
        changes["title"] = title
    if done is not None:
        changes["done"] = int(done)
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with conn:
            conn.execute(
                f"UPDATE todos SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (*changes.values(), todo_id),
            )
    return get_todo(conn, todo_id)


def delete_todo(conn: sqlite3.Connection, todo_id: int) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return cursor.rowcount > 0
