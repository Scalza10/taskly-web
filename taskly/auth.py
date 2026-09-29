"""Logins: the session cookie, the CurrentUser dependency, the /api account endpoints, and a
middleware that refuses cross-site writes, marks API answers uncacheable and renews cookies."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import passwords, sessions, users
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


Password = Annotated[str, Field(max_length=1024)]


class Login(BaseModel):
    username: str  # any length: login() refuses impossible names before they reach the throttle
    password: Password


class PasswordChange(BaseModel):
    current: Password
    new: Password


class LoginThrottle:
    """Password attempts in the last WINDOW seconds, per username and per client IP: failed
    ones and ones still being checked. attempt() checks and records in one step under a lock,
    so parallel guesses can't all slip past the limit; a right password takes its attempt back.

    In memory: right for one uvicorn process; a deploy resets it. More workers would
    need the counters in the database."""

    WINDOW = 15 * 60
    PER_USERNAME = 10
    PER_IP = 30

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.failures: dict[tuple[str, str], deque[float]] = {}
        self.lock = threading.Lock()

    def _keys(self, username: str | None, ip: str):
        keys = [(("ip", ip), self.PER_IP)]
        if username is not None:
            keys.insert(0, (("user", username.lower()), self.PER_USERNAME))
        return keys

    def _recent(self, key, now: float) -> deque[float]:
        times = self.failures.get(key, deque())
        while times and times[0] <= now - self.WINDOW:
            times.popleft()
        if not times:
            self.failures.pop(key, None)
        return times

    def attempt(self, username: str | None, ip: str) -> int:
        """0 if the attempt may go ahead, and then it counts as failed until succeeded() or
        release(); else the seconds to wait. username=None counts against the IP only."""
        with self.lock:
            now = self.clock()
            keys = self._keys(username, ip)
            wait = 0.0
            for key, limit in keys:
                times = self._recent(key, now)
                if len(times) >= limit:
                    wait = max(wait, times[-limit] + self.WINDOW - now)
            if wait > 0:
                return math.ceil(wait)
            for key, _ in keys:
                self.failures.setdefault(key, deque()).append(now)
            return 0

    def _take_back(self, key) -> None:
        # Drops the newest entry: every entry is failed or in flight, so the count stays exact.
        times = self.failures.get(key)
        if times:
            times.pop()
            if not times:
                del self.failures[key]

    def release(self, username: str, ip: str) -> None:
        """Take back an attempt whose password was right."""
        with self.lock:
            for key, _ in self._keys(username, ip):
                self._take_back(key)

    def succeeded(self, username: str, ip: str) -> None:
        """A good login: forget that name's failures and take back the attempt."""
        with self.lock:
            self.failures.pop(("user", username.lower()), None)
            self._take_back(("ip", ip))


def _attempt(request: Request, username: str | None) -> tuple[LoginThrottle, str]:
    """Count a password attempt, or answer 429."""
    throttle: LoginThrottle = request.app.state.login_throttle
    # The real visitor: uvicorn runs with --proxy-headers and only Caddy can reach it.
    ip = request.client.host if request.client else "unknown"
    wait = throttle.attempt(username, ip)
    if wait:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in up to 15 minutes.",
                            headers={"Retry-After": str(wait)})
    return throttle, ip


router = APIRouter(prefix="/api")


@router.post("/login", status_code=204)
def login(body: Login, request: Request, response: Response, conn: Conn) -> None:
    if not users.USERNAME.fullmatch(body.username):
        # No such user can exist. Counted against the IP only (a huge name never becomes a key)
        # and checked against the dummy hash, so it takes as long as any wrong login.
        _attempt(request, None)
        passwords.verify_password(body.password, passwords.DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    throttle, ip = _attempt(request, body.username)
    user = users.authenticate(conn, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    throttle.succeeded(body.username, ip)
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
    throttle, ip = _attempt(request, user["username"])
    # 403, not 401: the page treats 401 as "logged out".
    if users.authenticate(conn, user["username"], body.current) is None:
        raise HTTPException(status_code=403, detail="The current password is wrong")
    throttle.release(user["username"], ip)
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
    app.state.login_throttle = LoginThrottle()
    app.include_router(router)
    app.middleware("http")(_middleware)
