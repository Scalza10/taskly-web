"""/mcp: Taskly's tools for an AI agent (Claude, Gemini), as the user who connected it.

The MCP Python SDK speaks the protocol (Streamable HTTP, stateless, JSON answers). Its own auth
isn't used: Guard checks the bearer token from oauth_routes and puts the user in a context variable,
and every tool works with the same queries and the same rights as the page. Tool errors come back
as tool results (isError), never as HTTP errors.

Agents keep a copy of these tool names and arguments: add optional arguments, don't rename or drop."""

import contextvars
import sqlite3
from contextlib import asynccontextmanager, closing
from typing import Annotated, Literal
from uuid import UUID, uuid4

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import auth, db, lists, oauth, oauth_routes, snapshot, tasks
from .routes import ListName, Title
from .settings import Settings

INSTRUCTIONS = """Taskly holds the user's to-do lists, some shared with other people.
Call list_lists first to see the lists. Task ids come from list_tasks.
To close (finish, tick off) a task, call complete_task; done=false opens it again.
A task's status is new, progress (in progress, being worked on) or done; set_task_status moves it.
Lists can be named by id or by name."""

_user: contextvars.ContextVar[dict] = contextvars.ContextVar("taskly_mcp_user")

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def _my_lists(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT l.id, l.name FROM lists l JOIN list_members m ON m.list_id = l.id
           WHERE m.user_id = ? ORDER BY l.name COLLATE NOCASE, l.id""",
        (user_id,),
    ).fetchall()


def find_list(conn: sqlite3.Connection, user_id: int, ref: str) -> str:
    """The id of the user's list named by ref: its id, or its name (any case)."""
    ref = ref.strip()
    mine = _my_lists(conn, user_id)
    for row in mine:
        if row["id"] == ref.lower():
            return row["id"]
    named = [row for row in mine if row["name"].casefold() == ref.casefold()]
    if len(named) == 1:
        return named[0]["id"]
    if named:
        ids = ", ".join(row["id"] for row in named)
        raise ToolError(f'{len(named)} lists are called "{ref}". Name one by its id: {ids}')
    if not mine:
        raise ToolError("You have no lists yet. create_list makes one.")
    names = ", ".join(f'"{row["name"]}"' for row in mine)
    raise ToolError(f'You have no list called "{ref}". Your lists: {names}')


def _task(task: dict) -> dict:
    """A task as the agent sees it: list_id is implied by where it is."""
    return {key: task[key] for key in ("id", "title", "status", "done", "created_by", "done_by", "created_at")}


def _my_task(conn: sqlite3.Connection, user_id: int, task_id: str) -> dict:
    """The task, if it is in one of the user's lists; else a ToolError, the same for both cases."""
    try:
        task = tasks.get_task(conn, str(UUID(task_id)))
    except ValueError:
        task = None
    if task is None or lists.role(conn, task["list_id"], user_id) is None:
        raise ToolError("No such task. Task ids come from list_tasks.")
    return task


def build(settings: Settings) -> MCPServer:
    """The server and its tools, on settings' database."""
    server = MCPServer("Taskly", instructions=INSTRUCTIONS)

    def connection():
        return closing(db.connect(settings.db_path))

    @server.tool(annotations=READ)
    def list_lists() -> dict:
        """The user's lists: id, name, owner, the user's role, members, and how many tasks are open
        (not done, in progress included), in progress, and done."""
        user = _user.get()
        with connection() as conn:
            found = []
            for row in _my_lists(conn, user["id"]):
                open_, in_progress, done = conn.execute(
                    """SELECT COUNT(*) FILTER (WHERE status != 'done'), COUNT(*) FILTER (WHERE status = 'progress'),
                              COUNT(*) FILTER (WHERE status = 'done') FROM tasks WHERE list_id = ?""",
                    (row["id"],),
                ).fetchone()
                found.append({**snapshot.list_view(conn, row["id"], user["id"]),
                              "open": open_, "in_progress": in_progress, "done": done})
        return {"lists": found}

    @server.tool(annotations=READ)
    def list_tasks(
        list: Annotated[str | None, Field(description="A list's name or id. Leave out for every list.")] = None,
        include_done: Annotated[bool, Field(description="Also return finished tasks.")] = False,
    ) -> dict:
        """The open tasks (new or in progress) of one list, or of every list, oldest first.
        include_done adds the finished ones after them."""
        user = _user.get()
        with connection() as conn:
            ids = [find_list(conn, user["id"], list)] if list is not None else [r["id"] for r in _my_lists(conn, user["id"])]
            found = []
            for list_id in ids:
                view = snapshot.list_view(conn, list_id, user["id"])
                rows = [_task(t) for t in tasks.list_tasks(conn, list_id) if include_done or not t["done"]]
                found.append({"id": view["id"], "name": view["name"], "tasks": rows})
        return {"lists": found}

    @server.tool(annotations=WRITE)
    def create_list(name: Annotated[ListName, Field(description="The new list's name.")]) -> dict:
        """Create a list owned by the user. Add tasks to it with add_tasks."""
        user = _user.get()
        with connection() as conn:
            list_id = lists.create_list(conn, name, user["id"])
            return snapshot.list_view(conn, list_id, user["id"])

    @server.tool(annotations=WRITE)
    def add_tasks(
        list: Annotated[str, Field(description="The list's name or id.")],
        titles: Annotated[list[Title], Field(min_length=1, max_length=50, description="One title per task.")],
    ) -> dict:
        """Add tasks to a list, one per title. Returns the new tasks with their ids."""
        user = _user.get()
        with connection() as conn:
            list_id = find_list(conn, user["id"], list)
            added = []
            for title in titles:
                task, _ = tasks.create_task(conn, str(uuid4()), list_id, title, user["id"])
                added.append(_task(task))
            view = snapshot.list_view(conn, list_id, user["id"])
        return {"list": {"id": view["id"], "name": view["name"]}, "added": added}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                             openWorldHint=False))
    def complete_task(
        task_id: Annotated[str, Field(description="The task's id, from list_tasks.")],
        done: Annotated[bool, Field(description="false opens a finished task again.")] = True,
    ) -> dict:
        """Close (finish) a task, or open it again with done=false (a task in progress stays in progress)."""
        user = _user.get()
        with connection() as conn:
            task = _my_task(conn, user["id"], task_id)
            return _task(tasks.update_task(conn, task["id"], user["id"], done=done))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                             openWorldHint=False))
    def set_task_status(
        task_id: Annotated[str, Field(description="The task's id, from list_tasks.")],
        status: Annotated[Literal["new", "progress", "done"], Field(
            description="new, progress (in progress, being worked on) or done; done is the same as complete_task.")],
    ) -> dict:
        """Move a task to new, in progress or done, as on the page's board."""
        user = _user.get()
        with connection() as conn:
            task = _my_task(conn, user["id"], task_id)
            return _task(tasks.update_task(conn, task["id"], user["id"], status=status))

    return server


@asynccontextmanager
async def running(server: MCPServer):
    """The app's lifespan. A session manager runs only once, so each start makes a new one
    (tests start one app several times)."""
    server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        # Guard checks Origin; the SDK's Host check only knows localhost.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    async with server.session_manager.run():
        yield


class Guard:
    """ASGI app at /mcp: refuses a foreign Origin, needs a bearer token for this resource, then hands
    the request to the SDK with the token's user in _user."""

    def __init__(self, server: MCPServer, settings: Settings):
        self.server = server
        self.settings = settings

    def _token_user(self, token: str, resource: str) -> dict | None:
        with closing(db.connect(self.settings.db_path)) as conn:
            return oauth.token_user(conn, token, resource)

    async def __call__(self, scope, receive, send):
        request = Request(scope)
        no_store = {"Cache-Control": "no-store"}
        if not auth._same_origin(request):
            await JSONResponse({"detail": "Cross-site request refused"}, 403, headers=no_store)(scope, receive, send)
            return
        kind, _, token = request.headers.get("authorization", "").partition(" ")
        token = token.strip() if kind.lower() == "bearer" else ""
        user = await anyio.to_thread.run_sync(self._token_user, token, oauth_routes.mcp_url(request)) if token else None
        if user is None:
            metadata = oauth_routes.site(request) + "/.well-known/oauth-protected-resource/mcp"
            challenge = f'Bearer resource_metadata="{metadata}", scope="{oauth.SCOPE}"'
            if token:
                challenge += ', error="invalid_token", error_description="The token is wrong or expired"'
            body = {"error": "invalid_token" if token else "unauthorized", "error_description": "Connect Taskly again"}
            await JSONResponse(body, 401, headers={**no_store, "WWW-Authenticate": challenge})(scope, receive, send)
            return

        async def send_no_store(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        reset = _user.set(user)
        try:
            await self.server.session_manager.handle_request(scope, receive, send_no_store)
        finally:
            _user.reset(reset)
