"""The data endpoints: lists, their members, tasks, and GET /api/sync.

Every list or task action first asks the user's role in the list: none is a 404 (as if it
didn't exist, so ids can't be probed), a member doing an owner's action is a 403."""

import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, StringConstraints

from . import lists, snapshot, tasks, users
from .auth import CurrentUser
from .deps import Conn

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ListName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ListBody(BaseModel):
    name: ListName


class MemberBody(BaseModel):
    username: str


class TaskCreate(BaseModel):
    id: UUID
    list_id: UUID
    title: Title


class TaskUpdate(BaseModel):
    title: Title | None = None
    done: bool | None = None


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
        task, created = tasks.create_task(conn, str(body.id), str(body.list_id), body.title, user["id"])
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
    task = tasks.update_task(conn, str(task_id), user["id"], title=body.title, done=body.done)
    if task is None:  # deleted since task_for
        raise HTTPException(status_code=404, detail="No such task")
    return task


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, user: CurrentUser, conn: Conn) -> None:
    task_for(conn, task_id, user)
    tasks.delete_task(conn, str(task_id))
