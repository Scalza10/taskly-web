"""Queries on tasks. IDs are UUIDs made by the device, so creating is safe to retry.
Every function takes an open connection and returns plain dicts (status as 'new', 'progress' or
'done', plus done as a bool for older pages and agents; people by name)."""

import sqlite3

SELECT = """SELECT t.id, t.list_id, t.title, t.status, c.username AS created_by, d.username AS done_by,
                   t.created_at, t.updated_at
            FROM tasks t
            LEFT JOIN users c ON c.id = t.created_by
            LEFT JOIN users d ON d.id = t.done_by"""


def _to_dict(row: sqlite3.Row) -> dict:
    task = dict(row)
    task["done"] = task["status"] == "done"
    return task


def get_task(conn: sqlite3.Connection, task_id: str) -> dict | None:
    row = conn.execute(f"{SELECT} WHERE t.id = ?", (task_id,)).fetchone()
    return _to_dict(row) if row else None


def list_tasks(conn: sqlite3.Connection, list_id: str) -> list[dict]:
    # Not done first (in progress too), then oldest first; rowid breaks ties within the same second.
    rows = conn.execute(
        f"{SELECT} WHERE t.list_id = ? ORDER BY t.status = 'done', t.created_at, t.rowid", (list_id,)
    )
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
                done: bool | None = None, status: str | None = None) -> dict | None:
    """Changes only the fields given. status wins over done; done=False reopens only a done task
    (an older page unticking must not undo "in progress"). Finishing records who did it; any other
    status clears that. None if there is no such task."""
    assignments, values = [], []
    if title is not None:
        assignments.append("title = ?")
        values.append(title)
    if status is None and done is not None:
        status = "done" if done else None
        if not done:
            # Decided in the UPDATE itself, so a change made meanwhile is never overwritten.
            assignments.append("status = CASE WHEN status = 'done' THEN 'new' ELSE status END")
            assignments.append("done_by = CASE WHEN status = 'done' THEN NULL ELSE done_by END")
    if status is not None:
        assignments += ["status = ?", "done_by = ?"]
        values += [status, user_id if status == "done" else None]
    if assignments:
        with conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(assignments)}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                (*values, task_id),
            )
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0
