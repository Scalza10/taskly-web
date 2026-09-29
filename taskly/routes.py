from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints

from . import todos
from .auth import CurrentUser
from .deps import Conn

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class TodoCreate(BaseModel):
    title: Title


class TodoUpdate(BaseModel):
    title: Title | None = None
    done: bool | None = None


router = APIRouter()


@router.get("/health")
def health(conn: Conn) -> dict:
    # Touches the database, so a missing or broken volume shows up here. deploy.ps1 waits for "ok".
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/api/todos")
def list_todos(user: CurrentUser, conn: Conn) -> list[dict]:
    return todos.list_todos(conn)


@router.post("/api/todos", status_code=201)
def create_todo(body: TodoCreate, user: CurrentUser, conn: Conn) -> dict:
    return todos.create_todo(conn, body.title)


@router.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, user: CurrentUser, conn: Conn) -> dict:
    todo = todos.update_todo(conn, todo_id, title=body.title, done=body.done)
    if todo is None:
        raise HTTPException(status_code=404, detail="No such todo")
    return todo


@router.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, user: CurrentUser, conn: Conn) -> None:
    if not todos.delete_todo(conn, todo_id):
        raise HTTPException(status_code=404, detail="No such todo")
