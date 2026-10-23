"""Queries on tasks. IDs are UUIDs made by the device, so creating is safe to retry.
Every function takes an open connection and returns plain dicts (status as 'new', 'progress' or
'done', plus done as a bool for older pages and agents; people by name; due_date as '2026-10-17'
or None, with due_time as '15:00' in due_zone, the time zone it was set in, or both None; notes as
text or None, never ''; repeat as a rule like 'FREQ=WEEKLY;BYDAY=MO' (repeats.py) or None;
starred as a bool)."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from . import repeats

# update_task: leave this field as it is (None for due_date means "no due date", for notes "no notes",
# for repeat "it doesn't repeat").
KEEP = object()


class NoDueDate(ValueError):
    """A repeat needs a due date: the first day of its schedule."""


class IdTaken(Exception):
    """The id asked for a repeating task's next one is another task's."""


SELECT = """SELECT t.id, t.list_id, t.title, t.status, t.due_date, t.due_time, t.due_zone, t.notes, t.repeat,
                   t.starred, c.username AS created_by, d.username AS done_by, t.created_at, t.updated_at
            FROM tasks t
            LEFT JOIN users c ON c.id = t.created_by
            LEFT JOIN users d ON d.id = t.done_by"""


def _to_dict(row: sqlite3.Row) -> dict:
    task = dict(row)
    task["done"] = task["status"] == "done"
    task["starred"] = bool(task["starred"])
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
    # Not done first (in progress too); then the starred ones; then the ones with a due date, soonest
    # first; then oldest first, rowid breaking ties within the same second (sorted keeps that order
    # for equal keys).
    rows = conn.execute(f"{SELECT} WHERE t.list_id = ? ORDER BY t.created_at, t.rowid", (list_id,))
    found = [_to_dict(row) for row in rows]
    return sorted(found, key=lambda t: (t["done"], not t["starred"], t["due_date"] is None,
                                        _due_moment(t) if t["due_date"] else 0))


def create_task(conn: sqlite3.Connection, task_id: str, list_id: str, title: str, user_id: int,
                due_date: str | None = None, due_time: str | None = None,
                due_zone: str | None = None, notes: str | None = None,
                repeat: str | None = None, starred: bool = False) -> tuple[dict, bool]:
    """(task, created). If the id exists already (a device retrying), the stored task, unchanged.
    Empty notes are no notes, an empty repeat none; a repeat is anchored on the due date (NoDueDate without one)."""
    if repeat and not due_date:
        raise NoDueDate("A repeat needs a due date")
    try:
        with conn:
            conn.execute(
                "INSERT INTO tasks (id, list_id, title, created_by, due_date, due_time, due_zone, notes, repeat, starred)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, list_id, title, user_id, due_date, due_time, due_zone, notes or None,
                 repeats.anchored(repeat, due_date) if repeat else None, int(starred)),
            )
    except sqlite3.IntegrityError:
        existing = get_task(conn, task_id)
        if existing is None:  # not a duplicate id: the list vanished meanwhile
            raise
        return existing, False
    return get_task(conn, task_id), True


def update_task(conn: sqlite3.Connection, task_id: str, user_id: int, *, title: str | None = None,
                done: bool | None = None, status: str | None = None, due_date=KEEP,
                due_time: str | None = None, due_zone: str | None = None, notes=KEEP, repeat=KEEP,
                starred: bool | None = None, next_id: str | None = None, finished_on: str | None = None) -> dict | None:
    """Changes only the fields given. due_date replaces the due date as a whole, its due_time and
    due_zone too (None: no time); due_date=None removes it. notes=None or '' removes the notes.
    starred=None leaves the star; finishing doesn't remove it.
    repeat replaces the rule, anchored on the due date (None or '': it doesn't repeat; NoDueDate if
    there is no date). Moving the due date moves a rule anchored on it (repeats.moved); removing it
    stops the repeat.
    status wins over done; done=False reopens only a done task (an older page unticking must not
    undo "in progress").
    Finishing records who did it; any other status clears that. Finishing a repeating task makes the
    next one (_make_next). None if there is no such task."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")  # the task as it was, then the change, with no other write between
        before = get_task(conn, task_id)
        if before is None:
            return None
        assignments, values = [], []
        if title is not None:
            assignments.append("title = ?")
            values.append(title)
        due = before["due_date"] if due_date is KEEP else due_date
        if due_date is not KEEP:
            assignments += ["due_date = ?", "due_time = ?", "due_zone = ?"]
            values += [due_date, due_time, due_zone]
        if repeat is not KEEP and repeat and due is None:
            raise NoDueDate("A repeat needs a due date")
        if repeat is not KEEP:
            assignments.append("repeat = ?")
            values.append(repeats.anchored(repeat, due) if repeat else None)
        elif due_date is not KEEP and before["repeat"]:
            assignments.append("repeat = ?")
            values.append(repeats.moved(before["repeat"], before["due_date"], due) if due else None)
        if notes is not KEEP:
            assignments.append("notes = ?")
            values.append(notes or None)
        if starred is not None:
            assignments.append("starred = ?")
            values.append(int(starred))
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
            conn.execute(
                f"UPDATE tasks SET {', '.join(assignments)}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                (*values, task_id),
            )
        after = get_task(conn, task_id)
        if before["status"] != "done" and after["status"] == "done" and after["repeat"]:
            _make_next(conn, after, next_id, finished_on)
    return get_task(conn, task_id)


def _make_next(conn: sqlite3.Connection, task: dict, next_id: str | None, finished_on: str | None) -> None:
    """A repeating task was just finished: the next one, a copy (list, title, notes, time, zone, star,
    its author) due on the next day of the rule, new, with the rule, which this one gives up; so a
    series has one repeating task, and reopening this one doesn't make another. next_id: its id,
    made by the page so its copy and the server's agree (IdTaken if it's another task's); else a new
    one. finished_on: the finisher's date; else today_for. Inside update_task's transaction."""
    day = repeats.next_due(task["repeat"], task["due_date"], finished_on or repeats.today_for(task["due_zone"]))
    if day is not None:  # None past the year 9999: the series ends
        new_id = next_id or str(uuid4())
        if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (new_id,)).fetchone():
            raise IdTaken(new_id)
        conn.execute(
            "INSERT INTO tasks (id, list_id, title, created_by, due_date, due_time, due_zone, notes, repeat, starred)"
            " SELECT ?, list_id, title, created_by, ?, due_time, due_zone, notes, repeat, starred FROM tasks WHERE id = ?",
            (new_id, day, task["id"]),
        )
    conn.execute("UPDATE tasks SET repeat = NULL WHERE id = ?", (task["id"],))


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0


def delete_done(conn: sqlite3.Connection, list_id: str) -> list[dict]:
    """Deletes the list's finished tasks ("Clear done") and returns them as they were."""
    found = [task for task in list_tasks(conn, list_id) if task["done"]]
    with conn:
        # Still done: one reopened meanwhile stays.
        conn.executemany("DELETE FROM tasks WHERE id = ? AND status = 'done'", [(task["id"],) for task in found])
    return found
