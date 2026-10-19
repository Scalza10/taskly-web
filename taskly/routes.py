"""The data endpoints: lists, their members, tasks, and GET /api/sync.

Every list or task action first asks the user's role in the list: none is a 404 (as if it
didn't exist, so ids can't be probed), a member doing an owner's action is a 403."""

import sqlite3
import zoneinfo
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import AfterValidator, BaseModel, StringConstraints, model_validator

from . import lists, repeats, snapshot, tasks, users
from .auth import CurrentUser
from .deps import Conn

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ListName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def calendar_day(text: str) -> str:
    date.fromisoformat(text)  # 2026-02-30 is a ValueError, so a 422
    return text


def _time_zone(name: str) -> str:
    try:
        zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):  # a KeyError would be a 500
        raise ValueError("not a time zone") from None
    return name


# Only "2026-10-17": no times, timestamps or other forms. Stored as sent.
DueDate = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), AfterValidator(calendar_day)]
# A clock time, "15:00", in a due_zone: an IANA time zone name like "America/New_York".
DueTime = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
DueZone = Annotated[str, StringConstraints(max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+)*$"),
                    AfterValidator(_time_zone)]
# Plain text, line breaks kept. Empty after trimming is no notes (stored as NULL).
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
# How a task repeats (repeats.py), like "FREQ=WEEKLY;BYDAY=MO", made canonical. "" is no repeat.
Repeat = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(repeats.canonical)]


def due_problem(sent: set[str], due_date: str | None, due_time: str | None, due_zone: str | None) -> str | None:
    """What's wrong with a due date's parts (sent: the fields given), or None. Agents get the same rules."""
    if (due_time is None) != (due_zone is None):
        return "due_time and due_zone come together"
    if {"due_time", "due_zone"} & sent and "due_date" not in sent:
        return "send due_time and due_zone with their due_date"
    if due_time is not None and due_date is None:
        return "a due_time needs a due_date"
    return None


class Due(BaseModel):
    """A due date, and optionally its time in the zone it was set in. A time needs the date, in the same body."""
    due_date: DueDate | None = None
    due_time: DueTime | None = None
    due_zone: DueZone | None = None

    @model_validator(mode="after")
    def _time_with_date(self) -> "Due":
        problem = due_problem(self.model_fields_set, self.due_date, self.due_time, self.due_zone)
        if problem:
            raise ValueError(problem)
        return self


class DueRepeat(Due):
    """A new task's due date, and how it repeats from that day: a repeat needs the date."""
    repeat: Repeat | None = None

    @model_validator(mode="after")
    def _repeat_with_date(self) -> "DueRepeat":
        if self.repeat and self.due_date is None:
            raise ValueError("a repeat needs a due_date, its first day")
        return self


class ListBody(BaseModel):
    name: ListName


class MemberBody(BaseModel):
    username: str


class TaskCreate(DueRepeat):
    id: UUID
    list_id: UUID
    title: Title
    notes: Notes | None = None


class TaskUpdate(Due):  # due_date, notes or repeat: null removes it (and the date's time); left out, it stays
    title: Title | None = None
    notes: Notes | None = None  # "" removes them too
    repeat: Repeat | None = None  # "" removes it too, and so does removing the due date
    done: bool | None = None  # what pages before the board send; status wins if both are given
    status: Literal["new", "progress", "done"] | None = None
    # When this change finishes a repeating task: the next one's id (made by the page, so its copy
    # and the server's agree) and the day it was finished there. Left out, the server picks them.
    next_id: UUID | None = None
    finished_on: DueDate | None = None


router = APIRouter()


def require_role(conn, list_id: str, user: dict, *, owner: bool = False) -> str:
    role = lists.role(conn, list_id, user["id"])
    if role is None:
        raise HTTPException(status_code=404, detail="No such list")
    if owner and role != "owner":
        raise HTTPException(status_code=403, detail="Only the list's owner can do that")
    return role


def task_for(conn, task_id: UUID, user: dict) -> dict:
    task = tasks.get_task(conn, str(task_id))
    if task is None or lists.role(conn, task["list_id"], user["id"]) is None:
        raise HTTPException(status_code=404, detail="No such task")
    return task


@router.get("/health")
def health(conn: Conn) -> dict:
    # Touches the database, so a missing or broken volume shows up here. deploy.ps1 waits for "ok".
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/api/sync")
def sync(user: CurrentUser, conn: Conn) -> dict:
    return snapshot.snapshot(conn, user)


@router.post("/api/lists", status_code=201)
def create_list(body: ListBody, user: CurrentUser, conn: Conn) -> dict:
    return snapshot.list_view(conn, lists.create_list(conn, body.name, user["id"]), user["id"])


@router.patch("/api/lists/{list_id}")
def rename_list(list_id: UUID, body: ListBody, user: CurrentUser, conn: Conn) -> dict:
    require_role(conn, str(list_id), user, owner=True)
    if not lists.rename_list(conn, str(list_id), body.name):  # deleted since the role check
        raise HTTPException(status_code=404, detail="No such list")
    return snapshot.list_view(conn, str(list_id), user["id"])


@router.delete("/api/lists/{list_id}", status_code=204)
def delete_list(list_id: UUID, user: CurrentUser, conn: Conn) -> None:
    require_role(conn, str(list_id), user, owner=True)
    lists.delete_list(conn, str(list_id))


@router.post("/api/lists/{list_id}/members")
def add_member(list_id: UUID, body: MemberBody, response: Response, user: CurrentUser, conn: Conn) -> dict:
    require_role(conn, str(list_id), user, owner=True)
    name = body.username.strip()
    # Checked first: a name that can't be a username never reaches sqlite (a lone surrogate would be a 500).
    member = users.find_user(conn, name) if users.USERNAME.fullmatch(name) else None
    if member is None or member["disabled_at"]:
        raise HTTPException(status_code=404, detail="No such user")
    try:
        added = lists.add_member(conn, str(list_id), member["id"])
    except sqlite3.IntegrityError:  # the list was deleted since the role check
        raise HTTPException(status_code=404, detail="No such list") from None
    response.status_code = 201 if added else 200
    return snapshot.list_view(conn, str(list_id), user["id"])


@router.delete("/api/lists/{list_id}/members/{username}", status_code=204)
def remove_member(list_id: UUID, username: str, user: CurrentUser, conn: Conn) -> None:
    role = require_role(conn, str(list_id), user)
    member = users.find_user(conn, username)
    if member is None or lists.role(conn, str(list_id), member["id"]) is None:
        raise HTTPException(status_code=404, detail="Not a member")
    if member["id"] == user["id"]:
        if role == "owner":
            raise HTTPException(status_code=409, detail="The owner can't leave; delete the list instead")
    elif role != "owner":
        raise HTTPException(status_code=403, detail="Only the list's owner can do that")
    lists.remove_member(conn, str(list_id), member["id"])


@router.post("/api/tasks")
def create_task(body: TaskCreate, response: Response, user: CurrentUser, conn: Conn) -> dict:
    require_role(conn, str(body.list_id), user)
    try:
        task, created = tasks.create_task(conn, str(body.id), str(body.list_id), body.title, user["id"],
                                          body.due_date, body.due_time, body.due_zone, body.notes, body.repeat)
    except sqlite3.IntegrityError:  # the list was deleted since the role check
        raise HTTPException(status_code=404, detail="No such list") from None
    if task["list_id"] != str(body.list_id):
        raise HTTPException(status_code=409, detail="That task id is already used")
    # 200 for a retry: the device sent this create before but never got the answer.
    response.status_code = 201 if created else 200
    return task


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskUpdate, user: CurrentUser, conn: Conn) -> dict:
    task_for(conn, task_id, user)
    due_date = body.due_date if "due_date" in body.model_fields_set else tasks.KEEP
    notes = body.notes if "notes" in body.model_fields_set else tasks.KEEP
    repeat = body.repeat if "repeat" in body.model_fields_set else tasks.KEEP
    try:
        task = tasks.update_task(conn, str(task_id), user["id"], title=body.title, done=body.done, status=body.status,
                                 due_date=due_date, due_time=body.due_time, due_zone=body.due_zone, notes=notes,
                                 repeat=repeat, next_id=body.next_id and str(body.next_id), finished_on=body.finished_on)
    except tasks.NoDueDate as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except tasks.IdTaken:
        raise HTTPException(status_code=409, detail="That task id is already used") from None
    if task is None:  # deleted since task_for
        raise HTTPException(status_code=404, detail="No such task")
    return task


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, user: CurrentUser, conn: Conn) -> None:
    task_for(conn, task_id, user)
    tasks.delete_task(conn, str(task_id))
