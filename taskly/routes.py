import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints

from . import db, todos

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class TodoCreate(BaseModel):
    title: Title


class TodoUpdate(BaseModel):
    title: Title | None = None
    done: bool | None = None


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from db.session(request.app.state.settings.db_path)


Conn = Annotated[sqlite3.Connection, Depends(get_db)]

router = APIRouter()


@router.get("/health")
def health(conn: Conn) -> dict:
    # Touches the database, so a missing or broken volume shows up here. deploy.ps1 waits for "ok".
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/api/todos")
def list_todos(conn: Conn) -> list[dict]:
    return todos.list_todos(conn)


@router.post("/api/todos", status_code=201)
def create_todo(body: TodoCreate, conn: Conn) -> dict:
    return todos.create_todo(conn, body.title)


@router.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, conn: Conn) -> dict:
    todo = todos.update_todo(conn, todo_id, title=body.title, done=body.done)
    if todo is None:
        raise HTTPException(status_code=404, detail="No such todo")
    return todo


@router.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, conn: Conn) -> Response:
    if not todos.delete_todo(conn, todo_id):
        raise HTTPException(status_code=404, detail="No such todo")
    return Response(status_code=204)
