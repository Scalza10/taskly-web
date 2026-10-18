"""Queries on tasks. IDs are UUIDs made by the device, so creating is safe to retry.
Every function takes an open connection and returns plain dicts (status as 'new', 'progress' or
'done', plus done as a bool for older pages and agents; people by name; due_date as '2026-10-17'
or None, with due_time as '15:00' in due_zone, the time zone it was set in, or both None)."""

import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# update_task: leave this field as it is (None for due_date means "no due date").
KEEP = object()

SELECT = """SELECT t.id, t.list_id, t.title, t.status, t.due_date, t.due_time, t.due_zone,
                   c.username AS created_by, d.username AS done_by, t.created_at, t.updated_at
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


def _due_moment(task: dict) -> float:
    """When a task with a due date is due, as a timestamp: a time is a moment in its zone; a date
    alone counts as the end of that day, here in UTC (the server has no zone; each page uses its own)."""
    year, month, day = map(int, task["due_date"].split("-"))
    if task["due_time"]:
        hour, minute = map(int, task["due_time"].split(":"))
        return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(task["due_zone"])).timestamp()
    return datetime(year, month, day, tzinfo=UTC).timestamp() + 86400  # + a day: 9999-12-31 can't be a datetime


def list_tasks(conn: sqlite3.Connection, list_id: str) -> list[dict]:
    # Not done first (in progress too); then the ones with a due date, soonest first; then oldest
    # first, rowid breaking ties within the same second (sorted keeps that order for equal keys).
    rows = conn.execute(f"{SELECT} WHERE t.list_id = ? ORDER BY t.created_at, t.rowid", (list_id,))
    found = [_to_dict(row) for row in rows]
    return sorted(found, key=lambda t: (t["done"], t["due_date"] is None, _due_moment(t) if t["due_date"] else 0))


def create_task(conn: sqlite3.Connection, task_id: str, list_id: str, title: str, user_id: int,
                due_date: str | None = None, due_time: str | None = None,
                due_zone: str | None = None) -> tuple[dict, bool]:
    """(task, created). If the id exists already (a device retrying), the stored task, unchanged."""
    try:
        with conn:
            conn.execute(
                "INSERT INTO tasks (id, list_id, title, created_by, due_date, due_time, due_zone)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, list_id, title, user_id, due_date, due_time, due_zone),
            )
    except sqlite3.IntegrityError:
        existing = get_task(conn, task_id)
        if existing is None:  # not a duplicate id: the list vanished meanwhile
            raise
        return existing, False
    return get_task(conn, task_id), True


def update_task(conn: sqlite3.Connection, task_id: str, user_id: int, *, title: str | None = None,
                done: bool | None = None, status: str | None = None, due_date=KEEP,
                due_time: str | None = None, due_zone: str | None = None) -> dict | None:
    """Changes only the fields given. due_date replaces the due date as a whole, its due_time and
    due_zone too (None: no time); due_date=None removes it. status wins over done;
    done=False reopens only a done task (an older page unticking must not undo "in progress").
    Finishing records who did it; any other status clears that. None if there is no such task."""
    assignments, values = [], []
    if title is not None:
        assignments.append("title = ?")
        values.append(title)
    if due_date is not KEEP:
        assignments += ["due_date = ?", "due_time = ?", "due_zone = ?"]
        values += [due_date, due_time, due_zone]
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
