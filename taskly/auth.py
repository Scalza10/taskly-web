"""Logins: the session cookie, the CurrentUser dependency, the /api account endpoints, and a
middleware that refuses cross-site writes, marks API answers uncacheable and renews cookies."""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import sessions, users
from .deps import Conn

COOKIE = "taskly_session"
MAX_AGE = int(sessions.LIFETIME.total_seconds())
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def set_cookie(response: Response, request: Request, token: str) -> None:
    # Secure on https, which is every request behind Caddy (uvicorn trusts its X-Forwarded-Proto);
    # not on http://localhost, where the browser would otherwise drop it.
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, path="/", httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")


def clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=request.url.scheme == "https")


def current_user(request: Request, conn: Conn) -> dict:
    token = request.cookies.get(COOKIE)
    found = sessions.session_user(conn, token) if token else None
    if found is None:
        raise HTTPException(status_code=401, detail="Log in first")
    user, touched = found
    if touched:
        # The middleware re-sends the cookie, so its Max-Age follows the session's.
        request.state.renew_session = token
    return user


CurrentUser = Annotated[dict, Depends(current_user)]


class Login(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


router = APIRouter(prefix="/api")


@router.post("/login", status_code=204)
def login(body: Login, request: Request, response: Response, conn: Conn) -> None:
    user = users.authenticate(conn, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    device = sessions.device_label(request.headers.get("user-agent", ""))
    set_cookie(response, request, sessions.create_session(conn, user["id"], device))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, conn: Conn) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        sessions.delete_session(conn, token)
    clear_cookie(response, request)


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return {"username": user["username"]}


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChange, request: Request, user: CurrentUser, conn: Conn) -> None:
    # 403, not 401: the page treats 401 as "logged out".
    if users.authenticate(conn, user["username"], body.current) is None:
        raise HTTPException(status_code=403, detail="The current password is wrong")
    try:
        users.set_password(conn, user["id"], body.new)
    except users.UserError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    # Changing your password is how you sign out a lost phone.
    sessions.delete_user_sessions(conn, user["id"], keep_token=request.cookies.get(COOKIE))


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return origin is None or origin == f"{request.url.scheme}://{request.headers.get('host')}"


async def _middleware(request: Request, call_next):
    is_api = request.url.path.startswith("/api/")
    if is_api and request.method not in SAFE_METHODS and not _same_origin(request):
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403,
                            headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    if is_api:
        response.headers["Cache-Control"] = "no-store"
    token = getattr(request.state, "renew_session", None)
    if token:
        set_cookie(response, request, token)
    return response


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.middleware("http")(_middleware)
