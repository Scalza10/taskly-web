# Phase 1b: Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every person their own login (admin-created), keep them logged in per device for 90 days of use, record who added and who ticked off each todo, and replace Caddy's shared password.

**Architecture:** Migration 2 adds `users` and `sessions` and attribution columns on `todos`. Pure query modules (`passwords.py`, `users.py`, `sessions.py`) hold the logic; `auth.py` holds the FastAPI parts (cookie, `CurrentUser` dependency, login throttle, a middleware for the Origin check, `Cache-Control` and cookie renewal, and the `/api` account endpoints). `admin.py` is the command line for accounts. The React page gets a login screen and an account bar.

**Tech Stack:** Python 3.12, FastAPI, stdlib `sqlite3`/`hashlib.scrypt`/`secrets`, pytest; React 19 + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-28-accounts-lists-offline-design.md` (sections "Data model → Migration 2", "Accounts and security", "Deploying → Phase 1b rollout"). Phase **1b** of 4; requires phase 1a merged.

**Branch:** `phase-1b` off `main`.

## Global Constraints

- Only append to `MIGRATIONS`; never edit or reorder a deployed one. Migration 1 is deployed; migration 2 is new here.
- Timestamps: `strftime('%Y-%m-%dT%H:%M:%SZ', 'now')` in SQL, the same format in Python (`sessions.TIME_FORMAT`).
- Passwords: `hashlib.scrypt`, n=2**15, r=8, p=1, 16-byte salt, stored `scrypt$n$r$p$salt_hex$hash_hex`; compared with `hmac.compare_digest`; at least 10 characters.
- Session token: `secrets.token_urlsafe(32)`; the database stores only its SHA-256 hex.
- Cookie `taskly_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age` 90 days, `Secure` exactly when the request scheme is `https`.
- Sessions expire 90 days after last use; `last_used_at` written at most once an hour, and the cookie re-sent then.
- Login throttle: 10 failures per username, 30 per client IP, per 15 minutes; 429 with `Retry-After`.
- Non-GET `/api/*` with an `Origin` header that isn't `<scheme>://<host>` of the request: 403. No `Origin`: allowed.
- Every `/api/*` answer carries `Cache-Control: no-store`.
- Usernames: 2–32 of `A-Z a-z 0-9 . _ -`, case-insensitive.
- Endpoints that set cookies return `None` with `status_code=` in the decorator, never a `Response` object (FastAPI drops headers set on the injected `response` when an endpoint returns its own `Response`).
- Tests: `.venv\Scripts\python.exe -m pytest`; `npm --prefix frontend test`. Commits prefixed `feat:`/`fix:`/`docs:`.

## Review Focus

1. **A user types their name in different case** (`Maria` for `maria`): login works and the page shows the stored spelling. (Task 5 test.)
2. **An admin disables someone who is logged in:** their very next request is a 401, even with a valid cookie. (Task 3 and Task 5 tests.)
3. **Guessing the current password through "change password"** from a stolen session: counts toward the throttle like a failed login. (Task 6 test.)
4. **The site behind Caddy (https) vs local http:** the cookie is `Secure` only on https, so local runs keep working and production never sends it in clear. (Task 5 test.)
5. **A legit same-site request with a port** (the Vite dev server on `localhost:5173`): passes the Origin check; `https://evil.example` fails it. (Task 6 test.)

---

### Task 1: Migration 2

**Files:**
- Modify: `taskly/db.py` (append to `MIGRATIONS`)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces tables `users(id, username UNIQUE COLLATE NOCASE, password_hash, created_at, disabled_at)`, `sessions(token_hash PK, user_id → users ON DELETE CASCADE, device, created_at, last_used_at)`, index `sessions_user_id`, and columns `todos.created_by`, `todos.done_by` (→ users, NULL allowed).
- Produces test helper `migrate_to(path, version, monkeypatch)` in `tests/test_db.py`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
def migrate_to(path, version, monkeypatch):
    """Bring a database to exactly `version`, as an older deploy would have left it."""
    with monkeypatch.context() as m:
        m.setattr(db, "MIGRATIONS", db.MIGRATIONS[:version])
        db.migrate(path)


def test_migration_2_keeps_todos_and_adds_accounts(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 1, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO todos (title) VALUES ('from before accounts')")

    migrate_to(path, 2, monkeypatch)  # exactly 2: later migrations change todos again

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT title, created_by, done_by FROM todos").fetchall() == [
            ("from before accounts", None, None)
        ]
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('maria', 'x')")
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES ('MARIA', 'y')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("usernames must be unique regardless of case")
        conn.execute("INSERT INTO sessions (token_hash, user_id) VALUES ('h', 1)")
        assert conn.execute("SELECT device FROM sessions").fetchone() == ("",)
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_db.py -v`
Expected: `test_migration_2_keeps_todos_and_adds_accounts` FAILS with `no such column: created_by`.

- [ ] **Step 3: Append migration 2**

In `taskly/db.py`, add a second entry to `MIGRATIONS`, after the first one:

```python
    # 2: accounts. Users are disabled, never deleted, so "added by" survives.
    # Sessions store only the SHA-256 of the cookie's token.
    """
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT    NOT NULL,
        created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        disabled_at   TEXT
    );
    CREATE TABLE sessions (
        token_hash   TEXT    PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        device       TEXT    NOT NULL DEFAULT '',
        created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        last_used_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    CREATE INDEX sessions_user_id ON sessions(user_id);
    ALTER TABLE todos ADD COLUMN created_by INTEGER REFERENCES users(id);
    ALTER TABLE todos ADD COLUMN done_by    INTEGER REFERENCES users(id);
    """,
```

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (`test_migrate_runs_only_new_migrations` still works: it appends a third entry).

- [ ] **Step 5: Commit**

```bash
git add taskly/db.py tests/test_db.py
git commit -m "feat: migration 2, users and sessions"
```

---

### Task 2: Password hashing

**Files:**
- Create: `taskly/passwords.py`
- Test: `tests/test_passwords.py`
- Modify: `tests/conftest.py` (fast hashing in tests)

**Interfaces:**
- Produces: `passwords.hash_password(password: str) -> str`, `passwords.verify_password(password: str, stored: str) -> bool` (False for malformed `stored`), `passwords.MIN_LENGTH = 10`, `passwords.DUMMY_HASH: str`, module globals `N, R, P` read at call time.
- Produces: autouse fixture `fast_passwords` in `tests/conftest.py` setting `passwords.N = 2**4`.

- [ ] **Step 1: Write the failing tests**

`tests/test_passwords.py`:

```python
from taskly import passwords


def test_a_hash_verifies_only_its_own_password():
    stored = passwords.hash_password("purple-lamp-river")
    assert passwords.verify_password("purple-lamp-river", stored)
    assert not passwords.verify_password("purple-lamp-rivers", stored)


def test_the_hash_records_its_parameters_and_a_fresh_salt():
    first = passwords.hash_password("same password")
    second = passwords.hash_password("same password")
    scheme, n, r, p, salt, digest = first.split("$")
    assert (scheme, int(r), int(p)) == ("scrypt", 8, 1)
    assert int(n) == passwords.N
    assert len(bytes.fromhex(salt)) == 16
    assert first != second


def test_old_hashes_still_verify_after_the_cost_changes(monkeypatch):
    stored = passwords.hash_password("keep working")
    monkeypatch.setattr(passwords, "N", passwords.N * 2)
    assert passwords.verify_password("keep working", stored)


def test_malformed_hashes_never_verify():
    for stored in ["", "plain-password", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb", "scrypt$16$8$1$zz$bb"]:
        assert not passwords.verify_password("anything", stored)


def test_production_cost():
    # conftest lowers N for speed; the module's own default must stay 2**15.
    import importlib

    fresh = importlib.reload(passwords)
    try:
        assert (fresh.N, fresh.R, fresh.P) == (2**15, 8, 1)
    finally:
        importlib.reload(passwords)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_passwords.py -v`
Expected: FAIL, `ImportError: cannot import name 'passwords'`.

- [ ] **Step 3: Write `taskly/passwords.py`**

```python
"""Password hashing with stdlib scrypt.

Stored as scrypt$n$r$p$salt_hex$hash_hex, so the cost can be raised later without
breaking existing passwords: each hash is checked with its own parameters."""

import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1
MIN_LENGTH = 10


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # scrypt needs 128 * r * n bytes (32 MiB at the defaults), just over OpenSSL's default limit.
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=256 * r * n, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_scrypt(password, salt, N, R, P).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except ValueError:
        return False


# Checked when a username doesn't exist, so a wrong name takes as long as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
```

- [ ] **Step 4: Fast hashing in all tests**

`tests/conftest.py`, add:

```python
from taskly import passwords


@pytest.fixture(autouse=True)
def fast_passwords(monkeypatch):
    """scrypt at full cost takes ~100 ms per hash; tests hash a lot. test_passwords checks the real cost."""
    monkeypatch.setattr(passwords, "N", 2**4)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add taskly/passwords.py tests/test_passwords.py tests/conftest.py
git commit -m "feat: password hashing with scrypt"
```

---

### Task 3: Users and sessions queries

**Files:**
- Create: `taskly/users.py`, `taskly/sessions.py`
- Test: `tests/test_users.py`, `tests/test_sessions.py`
- Modify: `tests/conftest.py` (helpers)

**Interfaces:**
- Consumes: `passwords.hash_password`, `verify_password`, `DUMMY_HASH`, `MIN_LENGTH`.
- Produces (`users.py`):
  - `class UserError(ValueError)`: message is shown to people as is.
  - `check_username(name: str) -> None`, `check_password(password: str) -> None`: raise `UserError`.
  - `create_user(conn, username: str, password: str) -> dict`: raises `UserError` for bad or taken names.
  - `get_user(conn, user_id: int) -> dict | None`, `find_user(conn, username: str) -> dict | None` (disabled users included). User dicts: `{"id", "username", "created_at", "disabled_at"}`.
  - `authenticate(conn, username: str, password: str) -> dict | None`: None for unknown, wrong or disabled.
  - `set_password(conn, user_id: int, password: str) -> None` (raises `UserError`), `set_disabled(conn, user_id: int, disabled: bool) -> None`.
  - `list_users(conn) -> list[dict]`: user dicts plus `"sessions": int`, by username.
- Produces (`sessions.py`):
  - `LIFETIME = timedelta(days=90)`, `TOUCH_EVERY = timedelta(hours=1)`, `TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"`.
  - `create_session(conn, user_id: int, device: str = "") -> str` (returns the token; also deletes expired sessions).
  - `session_user(conn, token: str) -> tuple[dict, bool] | None`: `({"id", "username"}, touched)`; None if unknown, expired (and then deleted) or the user is disabled.
  - `delete_session(conn, token: str) -> None`, `delete_user_sessions(conn, user_id: int, keep_token: str | None = None) -> int`.
  - `device_label(user_agent: str) -> str`, e.g. `"Chrome on Android"`, `""` if unknown.
- Produces (`tests/conftest.py`): `PASSWORD = "correct-horse-battery"`, `add_user(settings, username, password=PASSWORD) -> dict`, fixture `conn(settings)` yielding a migrated connection.

- [ ] **Step 1: Test helpers**

`tests/conftest.py`, add:

```python
from contextlib import closing

from taskly import db, users

PASSWORD = "correct-horse-battery"


def add_user(settings, username, password=PASSWORD) -> dict:
    """Create an account straight in the database, as `taskly.admin add-user` would."""
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        return users.create_user(conn, username, password)


@pytest.fixture
def conn(settings):
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        yield conn
```

- [ ] **Step 2: Write the failing tests**

`tests/test_users.py`:

```python
import pytest

from taskly import users
from conftest import PASSWORD


def test_create_and_find_ignores_case(conn):
    maria = users.create_user(conn, "Maria", PASSWORD)
    assert maria["username"] == "Maria"
    assert maria["disabled_at"] is None
    assert users.find_user(conn, "maria")["id"] == maria["id"]


@pytest.mark.parametrize("name", ["m", "x" * 33, "has space", "émile", "a/b", ""])
def test_bad_usernames_are_refused(conn, name):
    with pytest.raises(users.UserError):
        users.create_user(conn, name, PASSWORD)


def test_names_are_unique_regardless_of_case(conn):
    users.create_user(conn, "maria", PASSWORD)
    with pytest.raises(users.UserError, match="already exists"):
        users.create_user(conn, "MARIA", PASSWORD)


def test_short_passwords_are_refused(conn):
    with pytest.raises(users.UserError, match="at least 10"):
        users.create_user(conn, "maria", "123456789")


def test_authenticate(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    assert users.authenticate(conn, "MARIA", PASSWORD)["id"] == maria["id"]
    assert users.authenticate(conn, "maria", "wrong password!") is None
    assert users.authenticate(conn, "nobody", PASSWORD) is None


def test_disabled_users_cannot_authenticate(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    users.set_disabled(conn, maria["id"], True)
    assert users.authenticate(conn, "maria", PASSWORD) is None
    assert users.get_user(conn, maria["id"])["disabled_at"] is not None
    users.set_disabled(conn, maria["id"], False)
    assert users.authenticate(conn, "maria", PASSWORD) is not None


def test_set_password(conn):
    maria = users.create_user(conn, "maria", PASSWORD)
    users.set_password(conn, maria["id"], "a brand new one")
    assert users.authenticate(conn, "maria", "a brand new one") is not None
    assert users.authenticate(conn, "maria", PASSWORD) is None
    with pytest.raises(users.UserError):
        users.set_password(conn, maria["id"], "short")


def test_list_users_counts_sessions(conn):
    from taskly import sessions

    maria = users.create_user(conn, "maria", PASSWORD)
    users.create_user(conn, "ann", PASSWORD)
    sessions.create_session(conn, maria["id"])
    listed = users.list_users(conn)
    assert [(u["username"], u["sessions"]) for u in listed] == [("ann", 0), ("maria", 1)]
```

`tests/test_sessions.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from taskly import sessions, users
from conftest import PASSWORD


@pytest.fixture
def maria(conn):
    return users.create_user(conn, "maria", PASSWORD)


def age(conn, token, delta):
    """Pretend the session was last used `delta` ago."""
    when = (datetime.now(timezone.utc) - delta).strftime(sessions.TIME_FORMAT)
    conn.execute("UPDATE sessions SET last_used_at = ? WHERE token_hash = ?", (when, sessions._hash(token)))
    conn.commit()


def test_a_new_session_finds_its_user(conn, maria):
    token = sessions.create_session(conn, maria["id"], "Firefox on Windows")
    user, touched = sessions.session_user(conn, token)
    assert user == {"id": maria["id"], "username": "maria"}
    assert touched is False


def test_only_the_hash_is_stored(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored != token
    assert len(stored) == 64


def test_unknown_tokens_find_nobody(conn, maria):
    sessions.create_session(conn, maria["id"])
    assert sessions.session_user(conn, "made-up") is None


def test_use_after_an_hour_touches_the_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    age(conn, token, timedelta(hours=2))
    assert sessions.session_user(conn, token)[1] is True
    assert sessions.session_user(conn, token)[1] is False  # just touched


def test_sessions_expire_90_days_after_last_use(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    age(conn, token, timedelta(days=89))
    assert sessions.session_user(conn, token) is not None
    age(conn, token, timedelta(days=91))
    assert sessions.session_user(conn, token) is None
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_a_new_login_cleans_up_expired_sessions(conn, maria):
    old = sessions.create_session(conn, maria["id"])
    age(conn, old, timedelta(days=100))
    sessions.create_session(conn, maria["id"])
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_disabled_users_have_no_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    users.set_disabled(conn, maria["id"], True)
    assert sessions.session_user(conn, token) is None


def test_delete_user_sessions_can_keep_one(conn, maria):
    keep = sessions.create_session(conn, maria["id"])
    gone = sessions.create_session(conn, maria["id"])
    assert sessions.delete_user_sessions(conn, maria["id"], keep_token=keep) == 1
    assert sessions.session_user(conn, keep) is not None
    assert sessions.session_user(conn, gone) is None


def test_delete_session(conn, maria):
    token = sessions.create_session(conn, maria["id"])
    sessions.delete_session(conn, token)
    assert sessions.session_user(conn, token) is None


@pytest.mark.parametrize("agent, label", [
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36", "Chrome on Android"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1", "Safari on iPhone"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36 Edg/129.0", "Edge on Windows"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox on Mac"),
    ("curl/8.9.1", ""),
])
def test_device_label(agent, label):
    assert sessions.device_label(agent) == label
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_users.py tests/test_sessions.py -v`
Expected: FAIL, `ImportError: cannot import name 'users'`.

- [ ] **Step 4: Write `taskly/users.py`**

```python
"""Queries on users. Usernames are case-insensitive (COLLATE NOCASE). Users are disabled, never deleted."""

import re
import sqlite3

from . import passwords

USERNAME = re.compile(r"[A-Za-z0-9._-]{2,32}")
COLUMNS = "id, username, created_at, disabled_at"


class UserError(ValueError):
    """A username or password that can't be used. The message is shown to people as is."""


def check_username(name: str) -> None:
    if not USERNAME.fullmatch(name):
        raise UserError("Usernames are 2-32 letters, digits, '.', '_' or '-'")


def check_password(password: str) -> None:
    if len(password) < passwords.MIN_LENGTH:
        raise UserError(f"Passwords need at least {passwords.MIN_LENGTH} characters")


def create_user(conn: sqlite3.Connection, username: str, password: str) -> dict:
    check_username(username)
    check_password(password)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, passwords.hash_password(password)),
            )
    except sqlite3.IntegrityError:
        raise UserError(f"{username} already exists") from None
    return get_user(conn, cursor.lastrowid)


def get_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def find_user(conn: sqlite3.Connection, username: str) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict | None:
    """The active user with this name and password, or None."""
    row = conn.execute(
        "SELECT id, password_hash, disabled_at FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        passwords.verify_password(password, passwords.DUMMY_HASH)
        return None
    if not passwords.verify_password(password, row["password_hash"]) or row["disabled_at"]:
        return None
    return get_user(conn, row["id"])


def set_password(conn: sqlite3.Connection, user_id: int, password: str) -> None:
    check_password(password)
    with conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (passwords.hash_password(password), user_id))


def set_disabled(conn: sqlite3.Connection, user_id: int, disabled: bool) -> None:
    with conn:
        conn.execute(
            "UPDATE users SET disabled_at = CASE WHEN ? THEN strftime('%Y-%m-%dT%H:%M:%SZ', 'now') END WHERE id = ?",
            (disabled, user_id),
        )


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT u.id, u.username, u.created_at, u.disabled_at,
                  (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id) AS sessions
           FROM users u ORDER BY u.username"""
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 5: Write `taskly/sessions.py`**

```python
"""Login sessions: one row per logged-in device, found by the SHA-256 of the cookie's token.

A session lasts LIFETIME from its last use. last_used_at is written at most every TOUCH_EVERY,
and session_user says when it was, so the cookie's Max-Age can be renewed at the same time."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

LIFETIME = timedelta(days=90)
TOUCH_EVERY = timedelta(hours=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format(when: datetime) -> str:
    return when.strftime(TIME_FORMAT)


def _parse(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT).replace(tzinfo=timezone.utc)


def create_session(conn: sqlite3.Connection, user_id: int, device: str = "") -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        # Timestamps in TIME_FORMAT sort as text, so this compares correctly.
        conn.execute("DELETE FROM sessions WHERE last_used_at < ?", (_format(_now() - LIFETIME),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, device) VALUES (?, ?, ?)", (_hash(token), user_id, device)
        )
    return token


def session_user(conn: sqlite3.Connection, token: str) -> tuple[dict, bool] | None:
    """The active user behind a token, and whether the session was just touched. None if there is none."""
    row = conn.execute(
        """SELECT s.token_hash, s.last_used_at, u.id, u.username
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND u.disabled_at IS NULL""",
        (_hash(token),),
    ).fetchone()
    if row is None:
        return None
    now = _now()
    idle = now - _parse(row["last_used_at"])
    if idle > LIFETIME:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
        return None
    touched = idle >= TOUCH_EVERY
    if touched:
        with conn:
            conn.execute("UPDATE sessions SET last_used_at = ? WHERE token_hash = ?", (_format(now), row["token_hash"]))
    return {"id": row["id"], "username": row["username"]}, touched


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))


def delete_user_sessions(conn: sqlite3.Connection, user_id: int, keep_token: str | None = None) -> int:
    """Log a user out everywhere, except the session of keep_token. Returns how many ended."""
    keep = _hash(keep_token) if keep_token else ""
    with conn:
        cursor = conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep))
    return cursor.rowcount


_BROWSERS = [("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")]
_SYSTEMS = [("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
            ("Macintosh", "Mac"), ("Linux", "Linux")]


def device_label(user_agent: str) -> str:
    """A short name for a browser, to tell sessions apart: "Chrome on Android". Empty if unknown."""
    browser = next((name for mark, name in _BROWSERS if mark in user_agent), None)
    system = next((name for mark, name in _SYSTEMS if mark in user_agent), None)
    return f"{browser} on {system}" if browser and system else ""
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add taskly/users.py taskly/sessions.py tests/test_users.py tests/test_sessions.py tests/conftest.py
git commit -m "feat: user and session queries"
```

---

### Task 4: The admin command

**Files:**
- Create: `taskly/admin.py`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `users.*`, `sessions.delete_user_sessions`, `db.migrate`, `Settings`.
- Produces: `admin.main(argv: list[str] | None = None, *, settings: Settings | None = None, prompt: Callable[[str], str] = getpass.getpass) -> int` (exit code). Subcommands: `add-user NAME`, `reset-password NAME`, `disable-user NAME`, `enable-user NAME`, `list-users`, `revoke-sessions NAME`. Errors print to stderr and return 1.
- Phase 2 extends `add-user` (claims unowned lists) and `disable-user` (hands over lists) at the marked lines.

- [ ] **Step 1: Write the failing tests**

`tests/test_admin.py`:

```python
from contextlib import closing

import pytest

from taskly import admin, db, sessions, users
from conftest import PASSWORD, add_user


def answers(*replies):
    """A stand-in for getpass that answers in order."""
    replies = list(replies)
    return lambda _question: replies.pop(0)


def run(settings, *argv, prompt=answers()):
    return admin.main(list(argv), settings=settings, prompt=prompt)


def open_db(settings):
    return closing(db.connect(settings.db_path))


def test_add_user_with_a_typed_password(settings):
    assert run(settings, "add-user", "maria", prompt=answers(PASSWORD, PASSWORD)) == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is not None


def test_add_user_generates_a_password_when_left_empty(settings, capsys):
    assert run(settings, "add-user", "maria", prompt=answers("")) == 0
    printed = capsys.readouterr().out
    password = printed.strip().splitlines()[-1].split(": ", 1)[1]
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", password) is not None


def test_add_user_refuses_mismatched_passwords(settings, capsys):
    assert run(settings, "add-user", "maria", prompt=answers(PASSWORD, PASSWORD + "x")) == 1
    assert "don't match" in capsys.readouterr().err


def test_add_user_refuses_a_taken_name(settings, capsys):
    add_user(settings, "maria")
    assert run(settings, "add-user", "MARIA", prompt=answers(PASSWORD, PASSWORD)) == 1
    assert "already exists" in capsys.readouterr().err


def test_reset_password_logs_out_everywhere(settings):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        token = sessions.create_session(conn, maria["id"])
    assert run(settings, "reset-password", "maria", prompt=answers("a new password", "a new password")) == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", "a new password") is not None
        assert sessions.session_user(conn, token) is None


def test_disable_and_enable(settings):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        token = sessions.create_session(conn, maria["id"])
    assert run(settings, "disable-user", "maria") == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is None
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert run(settings, "enable-user", "maria") == 0
    with open_db(settings) as conn:
        assert users.authenticate(conn, "maria", PASSWORD) is not None
        assert sessions.session_user(conn, token) is None  # the old session stays gone


def test_revoke_sessions(settings, capsys):
    maria = add_user(settings, "maria")
    with open_db(settings) as conn:
        sessions.create_session(conn, maria["id"])
        sessions.create_session(conn, maria["id"])
    assert run(settings, "revoke-sessions", "maria") == 0
    assert "2 sessions ended" in capsys.readouterr().out


def test_list_users(settings, capsys):
    add_user(settings, "maria")
    add_user(settings, "tom")
    run(settings, "disable-user", "tom")
    capsys.readouterr()
    assert run(settings, "list-users") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[:4] == ["maria", "active", "0", "sessions"]
    assert lines[1].split()[:2] == ["tom", "disabled"]


@pytest.mark.parametrize("command", ["reset-password", "disable-user", "enable-user", "revoke-sessions"])
def test_unknown_users_are_an_error(settings, capsys, command):
    assert run(settings, command, "nobody", prompt=answers(PASSWORD, PASSWORD)) == 1
    assert "No user nobody" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin.py -v`
Expected: FAIL, `ImportError: cannot import name 'admin'`.

- [ ] **Step 3: Write `taskly/admin.py`**

```python
"""Accounts from the command line. There is no sign-up page: the admin creates every account.

On the VM, in ~/taskly:  docker compose exec app python -m taskly.admin add-user maria
Locally:                 .venv\\Scripts\\python.exe -m taskly.admin add-user maria"""

import argparse
import getpass
import secrets
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing

from . import db, sessions, users
from .settings import Settings


class AdminError(Exception):
    """Stops the command with a message and exit code 1."""


def _user(conn: sqlite3.Connection, name: str) -> dict:
    user = users.find_user(conn, name)
    if user is None:
        raise AdminError(f"No user {name}")
    return user


def _ask_password(prompt: Callable[[str], str], allow_generated: bool) -> tuple[str, bool]:
    """(password, generated). Empty answer makes one if allowed."""
    first = prompt("Password (empty: make one up): " if allow_generated else "Password: ")
    if not first and allow_generated:
        return secrets.token_urlsafe(12), True
    if prompt("Again: ") != first:
        raise AdminError("The passwords don't match")
    return first, False


def add_user(conn, args, prompt) -> None:
    users.check_username(args.name)
    password, generated = _ask_password(prompt, allow_generated=True)
    user = users.create_user(conn, args.name, password)
    print(f"Created {user['username']}.")
    # Phase 2: claim unowned lists here.
    if generated:
        print(f"Password: {password}")


def reset_password(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    password, generated = _ask_password(prompt, allow_generated=True)
    users.set_password(conn, user["id"], password)
    ended = sessions.delete_user_sessions(conn, user["id"])
    print(f"New password for {user['username']}; {ended} sessions ended.")
    if generated:
        print(f"Password: {password}")


def disable_user(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    users.set_disabled(conn, user["id"], True)
    ended = sessions.delete_user_sessions(conn, user["id"])
    # Phase 2: hand over their lists here.
    print(f"Disabled {user['username']}; {ended} sessions ended.")


def enable_user(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    users.set_disabled(conn, user["id"], False)
    print(f"Enabled {user['username']}.")


def revoke_sessions(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    ended = sessions.delete_user_sessions(conn, user["id"])
    print(f"{user['username']}: {ended} sessions ended.")


def list_users(conn, args, prompt) -> None:
    for user in users.list_users(conn):
        state = "disabled" if user["disabled_at"] else "active"
        print(f"{user['username']:<32} {state:<8} {user['sessions']} sessions  (created {user['created_at']})")


COMMANDS = {
    "add-user": (add_user, "create an account"),
    "reset-password": (reset_password, "set a new password and log out everywhere"),
    "disable-user": (disable_user, "block logins and log out everywhere"),
    "enable-user": (enable_user, "allow logins again"),
    "revoke-sessions": (revoke_sessions, "log a user out everywhere"),
    "list-users": (list_users, "show every account"),
}


def main(argv: list[str] | None = None, *, settings: Settings | None = None,
         prompt: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog="python -m taskly.admin", description="Manage Taskly accounts.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        if name != "list-users":
            command.add_argument("name")
    args = parser.parse_args(argv)

    settings = settings or Settings()
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        try:
            COMMANDS[args.command][0](conn, args, prompt)
        except (AdminError, users.UserError) as error:
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Try it by hand**

Run: `.venv\Scripts\python.exe -m taskly.admin add-user me` (type a 10+ character password twice), then `.venv\Scripts\python.exe -m taskly.admin list-users`.
Expected: `Created me.`, then a line `me  active  0 sessions …`. Keep this account for Task 7.

- [ ] **Step 6: Commit**

```bash
git add taskly/admin.py tests/test_admin.py
git commit -m "feat: python -m taskly.admin for accounts"
```

---

### Task 5: Logging in: cookie, CurrentUser and the account endpoints

**Files:**
- Create: `taskly/deps.py` (the per-request connection, moved out of `routes.py`)
- Create: `taskly/auth.py`
- Modify: `taskly/routes.py`, `taskly/main.py`
- Test: `tests/test_auth.py`
- Modify: `tests/conftest.py` (`client` logs in; `anon` doesn't)

**Interfaces:**
- Produces (`deps.py`): `get_db(request) -> Iterator[sqlite3.Connection]`, `Conn = Annotated[sqlite3.Connection, Depends(get_db)]`.
- Produces (`auth.py`):
  - `COOKIE = "taskly_session"`, `MAX_AGE: int` (90 days in seconds).
  - `current_user(request, conn) -> dict` / `CurrentUser = Annotated[dict, Depends(current_user)]`: `{"id", "username"}` or 401 `"Log in first"`.
  - `router` (prefix `/api`): `POST /login`, `POST /logout`, `GET /me`, `POST /me/password` (Task 6 adds throttling to login and password).
  - `install(app: FastAPI) -> None`: adds the router, the middleware and `app.state.login_throttle`.
- Produces (`tests/conftest.py`): fixtures `app`, `anon` (no login), `client` (logged in as `maria`), and `login(client, username, password=PASSWORD)`.

- [ ] **Step 1: Move the connection dependency**

Create `taskly/deps.py`:

```python
"""FastAPI dependencies shared by the routers."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from . import db


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from db.session(request.app.state.settings.db_path)


Conn = Annotated[sqlite3.Connection, Depends(get_db)]
```

In `taskly/routes.py`, delete `get_db` and `Conn` (and the now-unused imports `sqlite3`, `Iterator`, `Depends`, `Request`, `db`) and add `from .deps import Conn`.

- [ ] **Step 2: Test fixtures**

`tests/conftest.py`, replace the `client` fixture with:

```python
@pytest.fixture
def app(settings):
    return create_app(settings)


def login(client, username, password=PASSWORD):
    response = client.post("/api/login", json={"username": username, "password": password})
    assert response.status_code == 204, response.text
    return response


@pytest.fixture
def anon(app):
    """A browser that hasn't logged in."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(app, settings):
    """A browser logged in as maria."""
    add_user(settings, "maria")
    with TestClient(app) as client:
        login(client, "maria")
        yield client
```

- [ ] **Step 3: Write the failing tests**

`tests/test_auth.py`:

```python
from fastapi.testclient import TestClient

from conftest import PASSWORD, add_user, login


def test_login_sets_a_safe_cookie(anon, settings):
    add_user(settings, "maria")
    response = login(anon, "maria")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("taskly_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=7776000" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie  # plain http, as on localhost


def test_over_https_the_cookie_is_secure(app, settings):
    add_user(settings, "maria")
    with TestClient(app, base_url="https://testserver") as client:
        assert "Secure" in login(client, "maria").headers["set-cookie"]


def test_me(client):
    assert client.get("/api/me").json() == {"username": "maria"}


def test_login_ignores_the_case_of_the_name(anon, settings):
    add_user(settings, "maria")
    login(anon, "MARIA")
    assert anon.get("/api/me").json() == {"username": "maria"}


def test_wrong_password_or_unknown_user_is_401(anon, settings):
    add_user(settings, "maria")
    for username, password in [("maria", "not the password"), ("nobody", PASSWORD)]:
        response = anon.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 401
        assert response.json()["detail"] == "Wrong username or password"
        assert "set-cookie" not in response.headers


def test_without_login_the_api_is_401_but_health_and_login_are_open(anon):
    assert anon.get("/api/me").status_code == 401
    assert anon.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"}).status_code == 401
    assert anon.get("/health").status_code == 200


def test_logout_ends_the_session(client):
    token = client.cookies.get("taskly_session")
    response = client.post("/api/logout")
    assert response.status_code == 204
    assert 'taskly_session=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]
    client.cookies.set("taskly_session", token)  # even with the old cookie kept
    assert client.get("/api/me").status_code == 401


def test_logout_without_a_session_is_fine(anon):
    assert anon.post("/api/logout").status_code == 204


def test_disabled_user_is_logged_out_at_once(client, conn):
    conn.execute("UPDATE users SET disabled_at = '2026-01-01T00:00:00Z' WHERE username = 'maria'")
    conn.commit()
    assert client.get("/api/me").status_code == 401


def test_the_cookie_is_renewed_when_the_session_is_touched(client, conn):
    assert "set-cookie" not in client.get("/api/me").headers  # used a moment ago
    conn.execute("UPDATE sessions SET last_used_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day')")
    conn.commit()
    response = client.get("/api/me")
    assert response.status_code == 200
    assert "Max-Age=7776000" in response.headers["set-cookie"]


def test_change_password_logs_out_other_devices(app, client, settings):
    with TestClient(app) as phone:
        login(phone, "maria")
        response = client.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"})
        assert response.status_code == 204
        assert phone.get("/api/me").status_code == 401
    assert client.get("/api/me").status_code == 200
    with TestClient(app) as laptop:
        login(laptop, "maria", "a brand new one")


def test_change_password_needs_the_current_one(client):
    response = client.post("/api/me/password", json={"current": "not it at all", "new": "a brand new one"})
    assert response.status_code == 403
    assert response.json()["detail"] == "The current password is wrong"


def test_change_password_refuses_a_short_one(client):
    response = client.post("/api/me/password", json={"current": PASSWORD, "new": "short"})
    assert response.status_code == 422
    assert "at least 10" in response.json()["detail"]


def test_api_answers_are_never_cached(client):
    assert client.get("/api/me").headers["cache-control"] == "no-store"
    assert "cache-control" not in client.get("/health").headers
```

- [ ] **Step 4: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL; the `login` helper gets 404 from `POST /api/login`.

- [ ] **Step 5: Write `taskly/auth.py`**

```python
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
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
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
```

(The Origin check and `Cache-Control` have tests in Task 6 and above; the throttle comes in Task 6.)

- [ ] **Step 6: Wire it in, and protect the todo routes**

`taskly/main.py`: `from . import auth, db, routes`, and in `create_app` call `auth.install(app)` right before `app.include_router(routes.router)`.

`taskly/routes.py`: `from .auth import CurrentUser`, and add `user: CurrentUser` as a parameter to `list_todos`, `create_todo`, `update_todo` and `delete_todo` (Task 7 uses it for attribution). Change `delete_todo` to not return a `Response` object:

```python
@router.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, user: CurrentUser, conn: Conn) -> None:
    if not todos.delete_todo(conn, todo_id):
        raise HTTPException(status_code=404, detail="No such todo")
```

(and drop the unused `Response` import).

- [ ] **Step 7: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass. `tests/test_api.py` tests use `client`, now logged in; `test_todos_survive_a_restart` builds its own clients, so change it to:

```python
def test_todos_survive_a_restart(settings):
    add_user(settings, "maria")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        add(client, "still here")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        assert [todo["title"] for todo in client.get("/api/todos").json()] == ["still here"]
```

with `from conftest import add_user, login, make_settings` at the top of `tests/test_api.py`.

- [ ] **Step 8: Commit**

```bash
git add taskly/deps.py taskly/auth.py taskly/routes.py taskly/main.py tests/conftest.py tests/test_auth.py tests/test_api.py
git commit -m "feat: log in with a session cookie; the API needs a login"
```

---

### Task 6: Login throttling and the Origin check

**Files:**
- Modify: `taskly/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `auth.LoginThrottle(clock: Callable[[], float] = time.monotonic)` with `WINDOW = 900`, `PER_USERNAME = 10`, `PER_IP = 30`, methods `retry_after(username: str, ip: str) -> int` (0 = allowed), `failed(username: str, ip: str) -> None`, `succeeded(username: str) -> None`. One instance per app at `app.state.login_throttle`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
from taskly.auth import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def fail(client, username="maria"):
    return client.post("/api/login", json={"username": username, "password": "not the password"})


def test_ten_failures_lock_that_username_for_a_while(app, anon, settings):
    add_user(settings, "maria")
    clock = Clock()
    app.state.login_throttle = LoginThrottle(clock)
    for _ in range(10):
        assert fail(anon).status_code == 401
    locked = anon.post("/api/login", json={"username": "maria", "password": PASSWORD})
    assert locked.status_code == 429
    assert 1 <= int(locked.headers["retry-after"]) <= 900
    clock.now += 901
    login(anon, "maria")


def test_the_lock_ignores_the_case_of_the_name(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for name in ["maria", "MARIA"] * 5:
        fail(anon, name)
    assert fail(anon, "Maria").status_code == 429


def test_thirty_failures_from_one_address_lock_every_name(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for i in range(30):
        fail(anon, f"guess{i}")
    assert anon.post("/api/login", json={"username": "maria", "password": PASSWORD}).status_code == 429


def test_a_good_login_clears_that_name_s_failures(app, anon, settings):
    add_user(settings, "maria")
    app.state.login_throttle = LoginThrottle(Clock())
    for _ in range(9):
        fail(anon)
    login(anon, "maria")
    for _ in range(9):
        assert fail(anon).status_code == 401


def test_wrong_current_passwords_count_as_failures(app, client):
    app.state.login_throttle = LoginThrottle(Clock())
    for _ in range(10):
        assert client.post("/api/me/password", json={"current": "guess guess", "new": "a brand new one"}).status_code == 403
    response = client.post("/api/me/password", json={"current": PASSWORD, "new": "a brand new one"})
    assert response.status_code == 429


def test_writes_from_another_site_are_refused(client):
    evil = {"Origin": "https://evil.example"}
    change = {"current": PASSWORD, "new": "a brand new one"}
    assert client.post("/api/me/password", json=change, headers=evil).status_code == 403
    assert client.post("/api/logout", headers=evil).status_code == 403
    assert client.get("/api/me").status_code == 200  # still logged in, password unchanged
    login(client, "maria")


def test_writes_from_the_same_origin_pass_even_with_a_port(app, settings):
    add_user(settings, "maria")
    with TestClient(app, base_url="http://localhost:5173") as client:
        login(client, "maria")
        response = client.post("/api/logout", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 204
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL, `ImportError: cannot import name 'LoginThrottle'`. (The two Origin tests would pass already; they pin Task 5's middleware.)

- [ ] **Step 3: Add the throttle**

In `taskly/auth.py`, add imports `import math`, `import time`, `from collections import deque`, `from collections.abc import Callable`, and above `router = …`:

```python
class LoginThrottle:
    """Failed logins in the last WINDOW seconds, per username and per client IP.

    In memory: right for one uvicorn process; a deploy resets it. More workers would
    need the counters in the database."""

    WINDOW = 15 * 60
    PER_USERNAME = 10
    PER_IP = 30

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.failures: dict[tuple[str, str], deque[float]] = {}

    def _keys(self, username: str, ip: str):
        return [(("user", username.lower()), self.PER_USERNAME), (("ip", ip), self.PER_IP)]

    def _recent(self, key) -> deque[float]:
        times = self.failures.get(key, deque())
        while times and times[0] <= self.clock() - self.WINDOW:
            times.popleft()
        if not times:
            self.failures.pop(key, None)
        return times

    def retry_after(self, username: str, ip: str) -> int:
        """Seconds until another attempt is allowed; 0 if it is allowed now."""
        wait = 0.0
        for key, limit in self._keys(username, ip):
            times = self._recent(key)
            if len(times) >= limit:
                wait = max(wait, times[-limit] + self.WINDOW - self.clock())
        return math.ceil(wait) if wait > 0 else 0

    def failed(self, username: str, ip: str) -> None:
        for key, _ in self._keys(username, ip):
            self.failures.setdefault(key, deque()).append(self.clock())

    def succeeded(self, username: str) -> None:
        self.failures.pop(("user", username.lower()), None)


def _check_throttle(request: Request, username: str) -> tuple[LoginThrottle, str]:
    throttle: LoginThrottle = request.app.state.login_throttle
    # The real visitor: uvicorn runs with --proxy-headers and only Caddy can reach it.
    ip = request.client.host if request.client else "unknown"
    wait = throttle.retry_after(username, ip)
    if wait:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.",
                            headers={"Retry-After": str(wait)})
    return throttle, ip
```

Replace `login` and the first lines of `change_password`:

```python
@router.post("/login", status_code=204)
def login(body: Login, request: Request, response: Response, conn: Conn) -> None:
    throttle, ip = _check_throttle(request, body.username)
    user = users.authenticate(conn, body.username, body.password)
    if user is None:
        throttle.failed(body.username, ip)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    throttle.succeeded(body.username)
    device = sessions.device_label(request.headers.get("user-agent", ""))
    set_cookie(response, request, sessions.create_session(conn, user["id"], device))


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChange, request: Request, user: CurrentUser, conn: Conn) -> None:
    throttle, ip = _check_throttle(request, user["username"])
    # 403, not 401: the page treats 401 as "logged out".
    if users.authenticate(conn, user["username"], body.current) is None:
        throttle.failed(user["username"], ip)
        raise HTTPException(status_code=403, detail="The current password is wrong")
    # … the rest unchanged
```

and in `install`, add `app.state.login_throttle = LoginThrottle()`.

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add taskly/auth.py tests/test_auth.py
git commit -m "feat: throttle password guessing"
```

---

### Task 7: Who added and who ticked off each todo

**Files:**
- Modify: `taskly/todos.py`, `taskly/routes.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: todo dicts gain `"created_by": str | None` and `"done_by": str | None` (usernames). `todos.create_todo(conn, title, user_id)`, `todos.update_todo(conn, todo_id, user_id, *, title=None, done=None)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`:

```python
def test_todos_record_who_added_and_who_ticked(app, client, settings):
    todo = add(client, "Buy milk")
    assert (todo["created_by"], todo["done_by"]) == ("maria", None)

    add_user(settings, "tom")
    with TestClient(app) as tom:
        login(tom, "tom")
        done = tom.patch(f"/api/todos/{todo['id']}", json={"done": True}).json()
        assert (done["created_by"], done["done_by"]) == ("maria", "tom")
        renamed = tom.patch(f"/api/todos/{todo['id']}", json={"title": "Buy oat milk"}).json()
        assert renamed["done_by"] == "tom"

    undone = client.patch(f"/api/todos/{todo['id']}", json={"done": False}).json()
    assert undone["done_by"] is None


def test_todos_need_a_login(anon):
    assert anon.get("/api/todos").status_code == 401
    assert anon.post("/api/todos", json={"title": "x"}).status_code == 401
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py::test_todos_record_who_added_and_who_ticked -v`
Expected: FAIL, `KeyError: 'created_by'`. (`test_todos_need_a_login` already passes: it pins Task 5.)

- [ ] **Step 3: Update `taskly/todos.py`**

Replace `COLUMNS`, `list_todos`, `get_todo`, `create_todo` and `update_todo`:

```python
# Authors by name, not id. Todos from before accounts have none.
SELECT = """SELECT t.id, t.title, t.done, t.created_at, t.updated_at,
                   c.username AS created_by, d.username AS done_by
            FROM todos t
            LEFT JOIN users c ON c.id = t.created_by
            LEFT JOIN users d ON d.id = t.done_by"""


def list_todos(conn: sqlite3.Connection) -> list[dict]:
    # Open ones first, then newest first.
    rows = conn.execute(f"{SELECT} ORDER BY t.done, t.id DESC").fetchall()
    return [_to_dict(row) for row in rows]


def get_todo(conn: sqlite3.Connection, todo_id: int) -> dict | None:
    row = conn.execute(f"{SELECT} WHERE t.id = ?", (todo_id,)).fetchone()
    return _to_dict(row) if row else None


def create_todo(conn: sqlite3.Connection, title: str, user_id: int) -> dict:
    with conn:
        cursor = conn.execute("INSERT INTO todos (title, created_by) VALUES (?, ?)", (title, user_id))
    return get_todo(conn, cursor.lastrowid)


def update_todo(conn: sqlite3.Connection, todo_id: int, user_id: int, *, title: str | None = None,
                done: bool | None = None) -> dict | None:
    """Changes only the fields given; ticking records who did it. None if there is no such todo."""
    changes = {}
    if title is not None:
        changes["title"] = title
    if done is not None:
        changes["done"] = int(done)
        changes["done_by"] = user_id if done else None
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with conn:
            conn.execute(
                f"UPDATE todos SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (*changes.values(), todo_id),
            )
    return get_todo(conn, todo_id)
```

- [ ] **Step 4: Pass the user in `taskly/routes.py`**

```python
@router.post("/api/todos", status_code=201)
def create_todo(body: TodoCreate, user: CurrentUser, conn: Conn) -> dict:
    return todos.create_todo(conn, body.title, user["id"])


@router.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, user: CurrentUser, conn: Conn) -> dict:
    todo = todos.update_todo(conn, todo_id, user["id"], title=body.title, done=body.done)
    if todo is None:
        raise HTTPException(status_code=404, detail="No such todo")
    return todo
```

- [ ] **Step 5: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add taskly/todos.py taskly/routes.py tests/test_api.py
git commit -m "feat: todos record who added and who ticked them"
```

---

### Task 8: Login screen, account bar and attribution on the page

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/TodoPage.tsx`, `frontend/src/TodoItem.tsx`, `frontend/src/style.css`
- Create: `frontend/src/Login.tsx`, `frontend/src/AccountBar.tsx`, `frontend/src/ChangePassword.tsx`, `frontend/src/messages.ts`
- Test: `frontend/src/messages.test.ts`

**Interfaces:**
- Consumes: `POST /api/login`, `POST /api/logout`, `GET /api/me`, `POST /api/me/password`; `ApiError`.
- Produces (`api.ts`): `type Me = { username: string }`; `Todo` gains `created_by: string | null; done_by: string | null`.
- Produces (`messages.ts`): `loginMessage(error: unknown): string`, `passwordMessage(error: unknown): string`, `isLoggedOut(error: unknown): boolean` (an `ApiError` with status 401).
- Produces: `TodoPage({ onLoggedOut }: { onLoggedOut: () => void })`; `App` holds `user: string | null | undefined` (undefined = still checking).

- [ ] **Step 1: Write the failing test**

`frontend/src/messages.test.ts`:

```ts
import { expect, test } from "vitest";
import { ApiError } from "./api";
import { isLoggedOut, loginMessage, passwordMessage } from "./messages";

test("login messages", () => {
  expect(loginMessage(new ApiError(401, "Wrong username or password"))).toBe("Wrong username or password.");
  expect(loginMessage(new ApiError(429, "Too many"))).toBe("Too many attempts. Try again in a few minutes.");
  expect(loginMessage(new TypeError("Failed to fetch"))).toBe("Can't reach Taskly. Check your connection.");
  expect(loginMessage(new ApiError(500, "POST /api/login failed (500)"))).toBe("POST /api/login failed (500)");
});

test("password messages", () => {
  expect(passwordMessage(new ApiError(403, "The current password is wrong"))).toBe("The current password is wrong.");
  expect(passwordMessage(new ApiError(422, "Passwords need at least 10 characters"))).toBe("Passwords need at least 10 characters.");
  expect(passwordMessage(new ApiError(429, "x"))).toBe("Too many attempts. Try again in a few minutes.");
});

test("only a 401 means logged out", () => {
  expect(isLoggedOut(new ApiError(401, "Log in first"))).toBe(true);
  expect(isLoggedOut(new ApiError(403, "x"))).toBe(false);
  expect(isLoggedOut(new TypeError("Failed to fetch"))).toBe(false);
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `Failed to resolve import "./messages"`.

- [ ] **Step 3: `messages.ts` and the types**

`frontend/src/messages.ts`:

```ts
// What to tell people when a login or password change fails.
import { ApiError } from "./api";

const TOO_MANY = "Too many attempts. Try again in a few minutes.";
const OFFLINE = "Can't reach Taskly. Check your connection.";

export function isLoggedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function loginMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return OFFLINE;
  if (error.status === 401) return "Wrong username or password.";
  if (error.status === 429) return TOO_MANY;
  return error.message;
}

export function passwordMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return OFFLINE;
  if (error.status === 429) return TOO_MANY;
  if (error.status === 403 || error.status === 422) return `${error.message}.`;
  return error.message;
}
```

`frontend/src/api.ts`: add `created_by: string | null;` and `done_by: string | null;` to `Todo`, and:

```ts
export type Me = { username: string };
```

- [ ] **Step 4: Run the test to see it pass**

Run: `npm --prefix frontend test`
Expected: PASS.

- [ ] **Step 5: The components**

`frontend/src/Login.tsx`:

```tsx
// Shown when there is no session. Accounts are made by the admin (python -m taskly.admin add-user).
import { useState, type FormEvent } from "react";
import { api, type Me } from "./api";
import { loginMessage } from "./messages";

export function Login({ onLoggedIn }: { onLoggedIn: (username: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("POST", "/api/login", { username: username.trim(), password });
      onLoggedIn((await api<Me>("GET", "/api/me")).username);
    } catch (e) {
      setError(loginMessage(e));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Taskly</h1>
      <form className="stack" onSubmit={submit}>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>Log in</button>
      </form>
    </main>
  );
}
```

`frontend/src/ChangePassword.tsx`:

```tsx
// Changing your password also logs out every other device (a lost phone, say).
import { useState, type FormEvent } from "react";
import { api } from "./api";
import { passwordMessage } from "./messages";

export function ChangePassword({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== again) return setError("The new passwords don't match.");
    try {
      await api("POST", "/api/me/password", { current, new: next });
      onDone();
    } catch (e) {
      setError(passwordMessage(e));
    }
  }

  return (
    <form className="stack panel" onSubmit={submit}>
      <label>
        Current password
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      </label>
      <label>
        New password (at least 10 characters)
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
      </label>
      <label>
        New password again
        <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
      </label>
      <p className="hint">Your other devices will be logged out.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit">Change password</button>
        <button type="button" className="plain" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}
```

`frontend/src/AccountBar.tsx`:

```tsx
// Who is logged in, with "Change password" and "Log out".
import { useState } from "react";
import { api } from "./api";
import { ChangePassword } from "./ChangePassword";

export function AccountBar({ username, onLoggedOut }: { username: string; onLoggedOut: () => void }) {
  const [changing, setChanging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function logout() {
    try {
      await api("POST", "/api/logout");
      onLoggedOut();
    } catch {
      // Only the server can end the session (the cookie is HttpOnly), so don't pretend.
      setError("Logging out needs a connection.");
    }
  }

  return (
    <>
      <div className="account">
        <span>{username}</span>
        <button type="button" className="plain" onClick={() => setChanging(!changing)}>Change password</button>
        <button type="button" className="plain" onClick={logout}>Log out</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {changing && <ChangePassword onDone={() => setChanging(false)} />}
    </>
  );
}
```

`frontend/src/App.tsx`:

```tsx
// Decides between the login screen and the list. undefined = still asking the server.
import { useEffect, useState } from "react";
import { api, type Me } from "./api";
import { AccountBar } from "./AccountBar";
import { Login } from "./Login";
import { isLoggedOut } from "./messages";
import { TodoPage } from "./TodoPage";

export function App() {
  const [user, setUser] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("GET", "/api/me").then(
      (me) => setUser(me.username),
      (e) => (isLoggedOut(e) ? setUser(null) : setError((e as Error).message)),
    );
  }, []);

  if (error) return <main><h1>Taskly</h1><p className="error" role="alert">{error}</p></main>;
  if (user === undefined) return null;
  if (user === null) return <Login onLoggedIn={setUser} />;
  return (
    <>
      <AccountBar username={user} onLoggedOut={() => setUser(null)} />
      <TodoPage onLoggedOut={() => setUser(null)} />
    </>
  );
}
```

`frontend/src/TodoPage.tsx`: change the signature to `export function TodoPage({ onLoggedOut }: { onLoggedOut: () => void })`, add `import { isLoggedOut } from "./messages";`, and in both `catch (e)` blocks (in `refresh` and `change`) use:

```ts
    } catch (e) {
      if (isLoggedOut(e)) return onLoggedOut();
      setError((e as Error).message);
    }
```

`frontend/src/TodoItem.tsx`: wrap the title in a block that also shows attribution. Replace the `{editing ? … : …}` expression with:

```tsx
      <div className="body">
        {editing ? (
          <input
            className="title"
            aria-label="title"
            defaultValue={todo.title}
            maxLength={500}
            autoFocus
            onKeyDown={onKeyDown}
            onBlur={onBlur}
          />
        ) : (
          <span className="title" onClick={() => setEditing(true)}>{todo.title}</span>
        )}
        {(todo.created_by || todo.done_by) && (
          <small className="by">
            {[todo.created_by && `added by ${todo.created_by}`, todo.done_by && `done by ${todo.done_by}`]
              .filter(Boolean)
              .join(" · ")}
          </small>
        )}
      </div>
```

`frontend/src/style.css`, append:

```css
/* Forms with one field per line: login, change password. */
.stack { display: flex; flex-direction: column; gap: 12px; }
.stack label { display: flex; flex-direction: column; gap: 4px; color: var(--muted); font-size: 14px; }
.stack input {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
  color: var(--text);
  font: inherit;
}
.panel { margin: 0 auto 20px; max-width: 560px; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); }
.row { display: flex; gap: 8px; }
.hint { margin: 0; color: var(--muted); font-size: 14px; }

button.plain { padding: 4px 8px; background: none; color: var(--accent); }
button:disabled { opacity: 0.6; cursor: default; }

.account {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  max-width: 560px;
  margin: 0 auto;
  padding: 12px 16px 0;
  color: var(--muted);
  font-size: 14px;
}
.account span { margin-right: auto; }

li .body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.by { color: var(--muted); font-size: 12px; }
```

and change the `.title` rule's `flex: 1;` to nothing (the `.body` wrapper now takes the space): `.title { overflow-wrap: anywhere; cursor: text; outline: none; }`.

- [ ] **Step 6: Typecheck, test, build**

Run: `npm --prefix frontend run build` and `npm --prefix frontend test`
Expected: no type errors; tests pass.

- [ ] **Step 7: Check it in the browser, like a user**

With uvicorn and `npm --prefix frontend run dev` running, open <http://localhost:5173/> in a private window:
- The login screen shows. A wrong password: "Wrong username or password." and the password field clears.
- Log in as the account from Task 4, typed in capitals: the bar shows the name in its stored spelling; old todos show no "added by".
- Add a todo: "added by <you>". Tick it: "added by <you> · done by <you>". Untick: the "done by" goes.
- Change password with a wrong current one: "The current password is wrong." With a good one: the panel closes. In another browser where you were logged in, the next click shows the login screen.
- Log out: the login screen. Reload: still the login screen.
- Stop uvicorn, click "Log out" while logged in: "Logging out needs a connection." and you stay on the list.
- DevTools → Application → Cookies: `taskly_session` is `HttpOnly`, `SameSite Lax`.
- Phone width: no horizontal scroll.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: login screen, account bar and who did what on the page"
```

---

### Task 9: README and CLAUDE.md

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `.env.example` (no change needed; verify)

- [ ] **Step 1: README, a new "Accounts" section** (after "## API", before "## Layout")

````markdown
## Accounts

There is no sign-up page: the admin creates every account. Hand passwords over
in person, not through chat.

On the VM, in `~/taskly` (`docker compose exec app python -m taskly.admin …`), or
locally (`.venv\Scripts\python.exe -m taskly.admin …`):

| To | Run |
|---|---|
| Create an account | `add-user maria`, then type the password twice, or press Enter to get a random one printed |
| Set a new password (also logs them out everywhere) | `reset-password maria` |
| Block someone (logs them out; their name stays on what they did) | `disable-user maria` |
| Let them back in | `enable-user maria` |
| Log someone out everywhere (a lost phone) | `revoke-sessions maria` |
| See everyone | `list-users` |

People can change their own password on the page; that also logs out their
other devices. Logins last 90 days from the last time the device was used.
After 10 wrong passwords for a name (or 30 from one address) in 15 minutes,
logins wait a few minutes.

**Locally:** create yourself an account once with
`.venv\Scripts\python.exe -m taskly.admin add-user me`, then log in on the page.
````

- [ ] **Step 2: README, "## API"**

Add these rows at the top of the table, and a note under it:

```markdown
| `POST /api/login` | `{"username", "password"}` | 204 and the session cookie; 401 if wrong; 429 after too many tries |
| `POST /api/logout` | | 204; ends this device's session |
| `GET /api/me` | | `{"username"}` |
| `POST /api/me/password` | `{"current", "new"}` | 204; logs out your other devices. 403 if `current` is wrong, 422 if `new` is under 10 characters |
```

```markdown
Every `/api` endpoint except login needs the session cookie (401 otherwise).
Writes from another site (an `Origin` header that isn't this site) get 403.
```

and in the todo description add `"created_by", "done_by"` (usernames, or `null`).

- [ ] **Step 3: README, the VM and Caddy**

In "### First deploy", replace step 3 and 4 with:

````markdown
3. **Add the site to Caddy.** Add this block to `~/proxy/Caddyfile` and apply it
   as in [Editing the Caddyfile](#editing-the-caddyfile):

   ```
   <site> {
       reverse_proxy taskly:8000
   }
   ```

   Caddy gets the certificate by itself within a minute.
4. **Create the accounts** as in [Accounts](#accounts) and open `https://<site>/`.
````

Add a new subsection at the end of "## Deploy":

````markdown
### Moving from Caddy's password to accounts (once, when phase 1b ships)

1. Deploy. Caddy still asks for its password, so for a few minutes people log in twice.
2. Create everyone's account (see [Accounts](#accounts)).
3. In `~/proxy/Caddyfile`, remove the `@protected` line and the `basic_auth { … }`
   block from the site's block, leaving `reverse_proxy taskly:8000`. Validate and
   reload as in [Editing the Caddyfile](#editing-the-caddyfile).
4. In a private browser window, `https://<site>/` shows Taskly's own login and no
   browser password prompt.
````

In "## Caddy: the address and the password": rename it to "## Caddy: the address"; change its intro sentence to say Caddy only does HTTPS and forwarding for Taskly now (logins are the app's); delete the subsections "Changing the password", "Adding or removing a login" and "Removing the password"; in "When something goes wrong" delete the rows for `base64-decoding password` and keep the others.

- [ ] **Step 4: CLAUDE.md**

- In "## Architecture", add a bullet after **Database**:

```markdown
- **Accounts.** `passwords.py` (scrypt), `users.py` and `sessions.py` are plain queries; `auth.py` is the FastAPI side: the `taskly_session` cookie, `CurrentUser` (every `/api` route but login uses it), the login throttle (in memory, one process) and a middleware that refuses cross-site writes (`Origin` ≠ `scheme://host`), sets `Cache-Control: no-store` on `/api` and renews the cookie. Accounts are made with `python -m taskly.admin`; there is no sign-up. `deps.py` holds `get_db`/`Conn`. Endpoints return `None` with `status_code=` in the decorator, never a `Response` object: FastAPI drops cookies set on the injected `response` otherwise.
```

- In "## Deployment (shared VM)", replace the **The site is behind Caddy's `basic_auth`** bullet with:

```markdown
- **The app does its own logins** (phase 1b). The site's Caddyfile block is only `reverse_proxy taskly:8000`; never add `basic_auth` back. README "Caddy: the address" is the how-to for the address and Caddy errors; keep it current when giving Caddy instructions.
```

- In "### Caddy on the shared VM", delete the two bullets about `basic_auth` hashes and routing hashes through `sed`/`echo` (no longer relevant), keep the others.
- In "### App", add: `- **Tests log in.** The `client` fixture is logged in as `maria`; `anon` isn't. `fast_passwords` (autouse) lowers scrypt's cost; `test_passwords` checks the real one.`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: accounts, and Caddy without basic_auth"
```

---

### Task 10: Deploy phase 1b

- [ ] **Step 1:** Merge `phase-1b` into `main`; both test suites pass on `main`.
- [ ] **Step 2:** `.\scripts\deploy.ps1`. Expected: `schema 1 -> 2`, then `Deployed. status=ok`.
- [ ] **Step 3:** Follow README "Moving from Caddy's password to accounts" on the VM, together with the user: create the accounts, then remove `basic_auth`.
- [ ] **Step 4:** On a phone: log in, add a todo, see "added by …", log out.
