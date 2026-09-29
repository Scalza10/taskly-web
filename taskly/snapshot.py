"""What a user can see, shaped as the page gets it: GET /api/sync returns snapshot();
list endpoints return list_view() of the list they changed."""

import sqlite3

from . import tasks


def list_view(conn: sqlite3.Connection, list_id: str, user_id: int) -> dict:
    row = conn.execute(
        "SELECT l.id, l.name, l.owner_id, o.username AS owner FROM lists l LEFT JOIN users o ON o.id = l.owner_id "
        "WHERE l.id = ?",
        (list_id,),
    ).fetchone()
    members = [
        r[0]
        for r in conn.execute(
            """SELECT u.username FROM list_members m JOIN users u ON u.id = m.user_id
               WHERE m.list_id = ? AND u.disabled_at IS NULL ORDER BY u.username COLLATE NOCASE""",
            (list_id,),
        )
    ]
    return {
        "id": row["id"],
        "name": row["name"],
        "owner": row["owner"],
        "role": "owner" if row["owner_id"] == user_id else "member",
        "members": members,
    }


def snapshot(conn: sqlite3.Connection, user: dict) -> dict:
    list_ids = [
        r[0]
        for r in conn.execute(
            """SELECT l.id FROM lists l JOIN list_members m ON m.list_id = l.id
               WHERE m.user_id = ? ORDER BY l.name COLLATE NOCASE, l.id""",
            (user["id"],),
        )
    ]
    return {
        "me": user["username"],
        "lists": [{**list_view(conn, list_id, user["id"]), "tasks": tasks.list_tasks(conn, list_id)} for list_id in list_ids],
    }
