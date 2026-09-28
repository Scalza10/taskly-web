# Phase 2: Named Lists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single todo list with named lists that have an owner and members, tasks with device-made UUIDs, and one read endpoint (`GET /api/sync`) that returns everything a user can see.

**Architecture:** Migration 3 creates `lists`, `list_members` and `tasks`, moves the old todos into a list "Taskly" and drops `todos`. Query modules `lists.py`, `tasks.py` and `snapshot.py` replace `todos.py`; `routes.py` checks a user's role in a list before every list or task action (non-member: 404, member doing an owner's action: 403). The page gets a list picker, a "New list" form and list settings, and reads everything from `/api/sync`.

**Tech Stack:** Python 3.12, FastAPI, stdlib `sqlite3`/`uuid`, pytest; React 19 + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-28-accounts-lists-offline-design.md` (sections "Data model → Migration 3", "Lists, tasks and permissions", "Frontend → Phase 1 and 2 behaviour"). Phase **2** of 4; requires phase 1b merged.

**Branch:** `phase-2` off `main`.

## Global Constraints

- Only append to `MIGRATIONS`. Migrations 1 and 2 are deployed; migration 3 is new here.
- IDs: UUID strings, lowercase with dashes (the format of `crypto.randomUUID()` and `str(uuid.uuid4())`). Lists get theirs from the server, tasks from the device.
- Not a member of a list: 404 for anything in or about it. A member doing an owner-only action: 403. Not logged in: 401.
- List names trimmed, 1–100 characters; task titles trimmed, 1–500 characters (422 otherwise).
- Users appear by username in every answer, never by internal id.
- The server sets `created_at`/`updated_at`; device clocks are never used.
- Tasks sort open first, then newest first (`done, created_at DESC, rowid DESC`); lists by name, case-insensitive.
- `POST /api/tasks` is retry-safe: the same `id` in the same list answers 200 with the stored task, unchanged.
- Endpoints return `None` with `status_code=` in the decorator, never a `Response` object (see phase 1b).
- Tests: `.venv\Scripts\python.exe -m pytest`; `npm --prefix frontend test`. Commits prefixed `feat:`/`fix:`/`docs:`.

## Review Focus

1. **The VM's database has todos but, at migration time, a user was disabled:** the disabled user is neither owner nor member of "Taskly". (Task 1 test.)
2. **Someone is removed from a list:** from their next request, the list and its tasks are 404 for them and gone from their `/api/sync`. (Task 4 test.)
3. **A retried create with a different title** (the device edited the title before the retry): 200 and the stored task, unchanged; the edit arrives as its own PATCH. (Task 4 test.)
4. **Disabling an owner whose earliest member is also disabled:** ownership skips to the next active member. (Task 2 test.)
5. **The list remembered on this device was deleted or left:** the page shows the first list instead of nothing. (Task 6 test.)

---

### Task 1: Migration 3

**Files:**
- Modify: `taskly/db.py` (append to `MIGRATIONS`)
- Modify: `tests/test_db.py`, `tests/test_backup.py` (stop using `todos`, which this migration drops)

**Interfaces:**
- Produces tables `lists(id TEXT PK, name, owner_id → users NULL, created_at, updated_at)`, `list_members(list_id → lists ON DELETE CASCADE, user_id → users, joined_at, PK(list_id, user_id))` with index `list_members_user_id`, `tasks(id TEXT PK, list_id → lists ON DELETE CASCADE, title, done, created_by, done_by, created_at, updated_at)` with index `tasks_list_id`. `todos` is dropped.
- Test helper `migrate_to(path, version, monkeypatch)` exists in `tests/test_db.py` (phase 1b).

- [ ] **Step 1: Make the existing tests independent of `todos`**

In `tests/test_db.py`:
- `test_migrate_twice_changes_nothing`: insert `INSERT INTO users (username, password_hash) VALUES ('keep', 'x')` instead of the todo, and check `SELECT username FROM users` gives `[("keep",)]`.
- `test_migrate_runs_only_new_migrations`: append `"CREATE TABLE extra (id INTEGER);"` instead of the `ALTER TABLE todos …`, and check `SELECT name FROM sqlite_master WHERE name = 'extra'` finds it.

In `tests/test_backup.py`, `test_backup_is_a_full_copy`: insert into `users` (`('keep me', 'x')`) and read `SELECT username FROM users`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_db.py`:

```python
import re

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def rows(path, sql):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql)]


def test_migration_3_moves_todos_into_the_taskly_list(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 2, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            INSERT INTO users (username, password_hash, disabled_at) VALUES ('ann', 'x', '2026-01-01T00:00:00Z');
            INSERT INTO users (username, password_hash) VALUES ('maria', 'x'), ('tom', 'x');
            INSERT INTO todos (title, done, created_by, done_by, created_at, updated_at) VALUES
                ('old', 1, 2, 3, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'),
                ('new', 0, NULL, NULL, '2026-02-01T00:00:00Z', '2026-02-01T00:00:00Z');
        """)

    assert db.migrate(path) == 3

    [taskly] = rows(path, "SELECT * FROM lists")
    assert taskly["name"] == "Taskly"
    assert UUID.fullmatch(taskly["id"])
    assert taskly["owner_id"] == 2  # maria: the oldest *active* user
    assert (taskly["created_at"], taskly["updated_at"]) == ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
    assert [r["user_id"] for r in rows(path, "SELECT user_id FROM list_members ORDER BY user_id")] == [2, 3]

    tasks = rows(path, "SELECT * FROM tasks ORDER BY created_at")
    assert [(t["title"], t["done"], t["created_by"], t["done_by"], t["created_at"], t["updated_at"]) for t in tasks] == [
        ("old", 1, 2, 3, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        ("new", 0, None, None, "2026-02-01T00:00:00Z", "2026-02-01T00:00:00Z"),
    ]
    assert all(t["list_id"] == taskly["id"] and UUID.fullmatch(t["id"]) for t in tasks)
    assert tasks[0]["id"] != tasks[1]["id"]
    assert rows(path, "SELECT name FROM sqlite_master WHERE name = 'todos'") == []


def test_migration_3_without_todos_makes_no_list(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 2, monkeypatch)
    db.migrate(path)
    assert rows(path, "SELECT * FROM lists") == []


def test_migration_3_without_users_leaves_the_list_unowned(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 2, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO todos (title) VALUES ('from before accounts')")
    db.migrate(path)
    [taskly] = rows(path, "SELECT * FROM lists")
    assert taskly["owner_id"] is None
    assert rows(path, "SELECT * FROM list_members") == []
    assert [t["title"] for t in rows(path, "SELECT title FROM tasks")] == ["from before accounts"]


def test_deleting_a_list_deletes_its_tasks_and_members(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with closing(db.connect(path)) as conn, conn:
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('maria', 'x')")
        conn.execute("INSERT INTO lists (id, name, owner_id) VALUES ('l1', 'Food', 1)")
        conn.execute("INSERT INTO list_members (list_id, user_id) VALUES ('l1', 1)")
        conn.execute("INSERT INTO tasks (id, list_id, title) VALUES ('t1', 'l1', 'Milk')")
        conn.execute("DELETE FROM lists WHERE id = 'l1'")
    assert rows(path, "SELECT * FROM tasks") == []
    assert rows(path, "SELECT * FROM list_members") == []
```

and add `from contextlib import closing` to the imports of `tests/test_db.py`.

- [ ] **Step 3: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_db.py -v`
Expected: the four new tests FAIL (`assert 2 == 3`, `no such table: lists`).

- [ ] **Step 4: Append migration 3**

In `taskly/db.py`, add a third entry to `MIGRATIONS`:

```python
    # 3: named lists. The old single list becomes "Taskly" (only if it had todos), owned by
    # the oldest active user, with every active user as a member; its todos become tasks.
    # IDs are version-4 UUIDs; (random() & 3) picks the variant digit without abs() overflow.
    """
    CREATE TABLE lists (
        id         TEXT    PRIMARY KEY,
        name       TEXT    NOT NULL,
        owner_id   INTEGER REFERENCES users(id),
        created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    CREATE TABLE list_members (
        list_id   TEXT    NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
        user_id   INTEGER NOT NULL REFERENCES users(id),
        joined_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        PRIMARY KEY (list_id, user_id)
    );
    CREATE INDEX list_members_user_id ON list_members(user_id);
    CREATE TABLE tasks (
        id         TEXT    PRIMARY KEY,
        list_id    TEXT    NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
        title      TEXT    NOT NULL,
        done       INTEGER NOT NULL DEFAULT 0,
        created_by INTEGER REFERENCES users(id),
        done_by    INTEGER REFERENCES users(id),
        created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    CREATE INDEX tasks_list_id ON tasks(list_id);

    INSERT INTO lists (id, name, owner_id, created_at, updated_at)
    SELECT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4'
           || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (random() & 3), 1)
           || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
           'Taskly',
           (SELECT MIN(id) FROM users WHERE disabled_at IS NULL),
           (SELECT MIN(created_at) FROM todos),
           (SELECT MAX(updated_at) FROM todos)
    WHERE EXISTS (SELECT 1 FROM todos);

    INSERT INTO list_members (list_id, user_id)
    SELECT lists.id, users.id FROM lists, users WHERE users.disabled_at IS NULL;

    INSERT INTO tasks (id, list_id, title, done, created_by, done_by, created_at, updated_at)
    SELECT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4'
           || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (random() & 3), 1)
           || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
           (SELECT id FROM lists), title, done, created_by, done_by, created_at, updated_at
    FROM todos ORDER BY id;

    DROP TABLE todos;
    """,
```

(`lists` is new, so at this point it holds at most the one "Taskly" row; `SELECT id FROM lists` is that row. With no users, `MIN(id)` is NULL and the members insert adds nothing. Tasks are inserted in old-id order, so `rowid` keeps the old order for ties in `created_at`.)

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_db.py tests/test_backup.py tests/test_migrate.py -v`
Expected: all pass. (The todo tests in `tests/test_api.py` now fail, since `todos` is gone; Task 4 replaces them. Don't commit a red suite: go straight on to Step 6.)

- [ ] **Step 6: Commit (with the todo tests skipped until Task 4)**

Mark `tests/test_api.py` with `pytestmark = pytest.mark.skip(reason="replaced in phase 2, task 4")` at the top (add `import pytest`), run `.venv\Scripts\python.exe -m pytest -q` (expected: all pass or skipped), then:

```bash
git add taskly/db.py tests/test_db.py tests/test_backup.py tests/test_api.py
git commit -m "feat: migration 3, named lists and tasks with UUIDs"
```

---

### Task 2: List queries

**Files:**
- Create: `taskly/lists.py`
- Test: `tests/test_lists.py`

**Interfaces:**
- Produces:
  - `role(conn, list_id: str, user_id: int) -> str | None`: `"owner"`, `"member"` or None.
  - `create_list(conn, name: str, owner_id: int) -> str` (new id; the owner is added as a member).
  - `rename_list(conn, list_id: str, name: str) -> None`, `delete_list(conn, list_id: str) -> None`.
  - `add_member(conn, list_id: str, user_id: int) -> bool` (False if already a member), `remove_member(conn, list_id: str, user_id: int) -> bool`.
  - `claim_unowned(conn, user_id: int) -> list[str]`: makes the user owner and member of every list without an owner; returns their names.
  - `hand_over(conn, user_id: int) -> list[tuple[str, str]]`: each list the user owns passes to its earliest-joined *active* other member; returns `(list name, new owner's username)`; lists with no such member are left alone.

- [ ] **Step 1: Write the failing tests**

`tests/test_lists.py`:

```python
import pytest

from taskly import lists, users
from conftest import PASSWORD


@pytest.fixture
def people(conn):
    return {name: users.create_user(conn, name, PASSWORD)["id"] for name in ["maria", "tom", "ann", "zoe"]}


def test_the_creator_owns_the_list_and_is_a_member(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    assert lists.role(conn, list_id, people["maria"]) == "owner"
    assert lists.role(conn, list_id, people["tom"]) is None


def test_members(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    assert lists.add_member(conn, list_id, people["tom"]) is True
    assert lists.add_member(conn, list_id, people["tom"]) is False
    assert lists.role(conn, list_id, people["tom"]) == "member"
    assert lists.remove_member(conn, list_id, people["tom"]) is True
    assert lists.remove_member(conn, list_id, people["tom"]) is False
    assert lists.role(conn, list_id, people["tom"]) is None


def test_rename_and_delete(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    lists.rename_list(conn, list_id, "Food")
    assert conn.execute("SELECT name FROM lists WHERE id = ?", (list_id,)).fetchone()[0] == "Food"
    lists.delete_list(conn, list_id)
    assert lists.role(conn, list_id, people["maria"]) is None


def test_the_first_user_claims_unowned_lists(conn, people):
    conn.execute("INSERT INTO lists (id, name) VALUES ('legacy', 'Taskly')")
    conn.commit()
    assert lists.claim_unowned(conn, people["maria"]) == ["Taskly"]
    assert lists.role(conn, "legacy", people["maria"]) == "owner"
    assert lists.claim_unowned(conn, people["tom"]) == []


def test_hand_over_goes_to_the_earliest_active_member(conn, people):
    list_id = lists.create_list(conn, "Groceries", people["maria"])
    for name in ["ann", "tom", "zoe"]:
        lists.add_member(conn, list_id, people[name])
    users.set_disabled(conn, people["ann"], True)  # joined first, but disabled

    assert lists.hand_over(conn, people["maria"]) == [("Groceries", "tom")]
    assert lists.role(conn, list_id, people["tom"]) == "owner"
    assert lists.role(conn, list_id, people["maria"]) == "member"


def test_hand_over_leaves_lists_nobody_else_is_in(conn, people):
    list_id = lists.create_list(conn, "Private", people["maria"])
    assert lists.hand_over(conn, people["maria"]) == []
    assert lists.role(conn, list_id, people["maria"]) == "owner"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lists.py -v`
Expected: FAIL, `ImportError: cannot import name 'lists'`.

- [ ] **Step 3: Write `taskly/lists.py`**

```python
"""Queries on lists and their members. The owner always has a member row too, so
"which lists can I see" is one lookup in list_members."""

import sqlite3
import uuid

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def role(conn: sqlite3.Connection, list_id: str, user_id: int) -> str | None:
    row = conn.execute(
        """SELECT l.owner_id FROM list_members m JOIN lists l ON l.id = m.list_id
           WHERE m.list_id = ? AND m.user_id = ?""",
        (list_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return "owner" if row["owner_id"] == user_id else "member"


def create_list(conn: sqlite3.Connection, name: str, owner_id: int) -> str:
    list_id = str(uuid.uuid4())
    with conn:
        conn.execute("INSERT INTO lists (id, name, owner_id) VALUES (?, ?, ?)", (list_id, name, owner_id))
        conn.execute("INSERT INTO list_members (list_id, user_id) VALUES (?, ?)", (list_id, owner_id))
    return list_id


def rename_list(conn: sqlite3.Connection, list_id: str, name: str) -> None:
    with conn:
        conn.execute(f"UPDATE lists SET name = ?, updated_at = {NOW} WHERE id = ?", (name, list_id))


def delete_list(conn: sqlite3.Connection, list_id: str) -> None:
    """Its tasks and member rows go with it (ON DELETE CASCADE)."""
    with conn:
        conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))


def add_member(conn: sqlite3.Connection, list_id: str, user_id: int) -> bool:
    with conn:
        cursor = conn.execute("INSERT OR IGNORE INTO list_members (list_id, user_id) VALUES (?, ?)", (list_id, user_id))
    return cursor.rowcount == 1


def remove_member(conn: sqlite3.Connection, list_id: str, user_id: int) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM list_members WHERE list_id = ? AND user_id = ?", (list_id, user_id))
    return cursor.rowcount == 1


def claim_unowned(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Lists without an owner (the old list, migrated before anyone had an account) go to this user."""
    names = [row[0] for row in conn.execute("SELECT name FROM lists WHERE owner_id IS NULL ORDER BY name")]
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO list_members (list_id, user_id) SELECT id, ? FROM lists WHERE owner_id IS NULL",
            (user_id,),
        )
        conn.execute("UPDATE lists SET owner_id = ? WHERE owner_id IS NULL", (user_id,))
    return names


def hand_over(conn: sqlite3.Connection, user_id: int) -> list[tuple[str, str]]:
    """Before disabling a user: each list they own passes to the active member who joined earliest."""
    moved = []
    for owned in conn.execute("SELECT id, name FROM lists WHERE owner_id = ? ORDER BY name", (user_id,)).fetchall():
        heir = conn.execute(
            """SELECT u.id, u.username FROM list_members m JOIN users u ON u.id = m.user_id
               WHERE m.list_id = ? AND m.user_id != ? AND u.disabled_at IS NULL
               ORDER BY m.joined_at, m.rowid LIMIT 1""",
            (owned["id"], user_id),
        ).fetchone()
        if heir:
            with conn:
                conn.execute(f"UPDATE lists SET owner_id = ?, updated_at = {NOW} WHERE id = ?", (heir["id"], owned["id"]))
            moved.append((owned["name"], heir["username"]))
    return moved
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lists.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskly/lists.py tests/test_lists.py
git commit -m "feat: list and member queries"
```

---

### Task 3: Task queries and the snapshot

**Files:**
- Create: `taskly/tasks.py`, `taskly/snapshot.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `lists.create_list`, `lists.add_member`.
- Produces (`tasks.py`): task dicts `{"id", "list_id", "title", "done": bool, "created_by": str | None, "done_by": str | None, "created_at", "updated_at"}`.
  - `get_task(conn, task_id: str) -> dict | None`, `list_tasks(conn, list_id: str) -> list[dict]` (sorted as in Global Constraints).
  - `create_task(conn, task_id: str, list_id: str, title: str, user_id: int) -> tuple[dict, bool]` (`created` is False when the id already existed; the returned task is then the stored one, possibly in another list).
  - `update_task(conn, task_id: str, user_id: int, *, title: str | None = None, done: bool | None = None) -> dict | None`, `delete_task(conn, task_id: str) -> bool`.
- Produces (`snapshot.py`):
  - `list_view(conn, list_id: str, user_id: int) -> dict`: `{"id", "name", "owner": str | None, "role", "members": [usernames of active members, by name]}`.
  - `snapshot(conn, user: dict) -> dict`: `{"me": username, "lists": [list_view + "tasks": list_tasks]}`, lists the user is a member of, by name.

- [ ] **Step 1: Write the failing tests**

`tests/test_tasks.py`:

```python
import uuid

import pytest

from taskly import lists, snapshot, tasks, users
from conftest import PASSWORD


@pytest.fixture
def maria(conn):
    return users.create_user(conn, "maria", PASSWORD)


@pytest.fixture
def tom(conn):
    return users.create_user(conn, "tom", PASSWORD)


@pytest.fixture
def groceries(conn, maria):
    return lists.create_list(conn, "Groceries", maria["id"])


def new_id():
    return str(uuid.uuid4())


def test_create_returns_the_task_with_its_author(conn, maria, groceries):
    task_id = new_id()
    task, created = tasks.create_task(conn, task_id, groceries, "Milk", maria["id"])
    assert created is True
    assert task["id"] == task_id and task["list_id"] == groceries
    assert (task["title"], task["done"], task["created_by"], task["done_by"]) == ("Milk", False, "maria", None)
    assert task["created_at"].endswith("Z")


def test_creating_the_same_id_again_changes_nothing(conn, maria, groceries):
    task_id = new_id()
    tasks.create_task(conn, task_id, groceries, "Milk", maria["id"])
    task, created = tasks.create_task(conn, task_id, groceries, "Oat milk", maria["id"])
    assert created is False
    assert task["title"] == "Milk"
    assert len(tasks.list_tasks(conn, groceries)) == 1


def test_update_records_who_ticked(conn, maria, tom, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    done = tasks.update_task(conn, task["id"], tom["id"], done=True)
    assert (done["done"], done["done_by"]) == (True, "tom")
    renamed = tasks.update_task(conn, task["id"], maria["id"], title="Oat milk")
    assert (renamed["title"], renamed["done_by"]) == ("Oat milk", "tom")
    undone = tasks.update_task(conn, task["id"], maria["id"], done=False)
    assert undone["done_by"] is None
    assert tasks.update_task(conn, new_id(), maria["id"], done=True) is None


def test_delete(conn, maria, groceries):
    task, _ = tasks.create_task(conn, new_id(), groceries, "Milk", maria["id"])
    assert tasks.delete_task(conn, task["id"]) is True
    assert tasks.delete_task(conn, task["id"]) is False


def test_tasks_sort_open_first_then_newest(conn, maria, groceries):
    ids = {}
    for title in ["first", "second", "third"]:
        ids[title] = tasks.create_task(conn, new_id(), groceries, title, maria["id"])[0]["id"]
    tasks.update_task(conn, ids["third"], maria["id"], done=True)
    # All three share a created_at second; insertion order breaks the tie.
    assert [t["title"] for t in tasks.list_tasks(conn, groceries)] == ["second", "first", "third"]


def test_snapshot_has_only_my_lists_with_members_and_tasks(conn, maria, tom, groceries):
    lists.add_member(conn, groceries, tom["id"])
    lists.create_list(conn, "tom's own", tom["id"])
    lists.create_list(conn, "apples", maria["id"])
    tasks.create_task(conn, new_id(), groceries, "Milk", tom["id"])

    seen = snapshot.snapshot(conn, maria)
    assert seen["me"] == "maria"
    assert [l["name"] for l in seen["lists"]] == ["apples", "Groceries"]  # case-insensitive
    shared = seen["lists"][1]
    assert (shared["owner"], shared["role"], shared["members"]) == ("maria", "owner", ["maria", "tom"])
    assert [t["title"] for t in shared["tasks"]] == ["Milk"]
    assert snapshot.snapshot(conn, tom)["lists"][0]["role"] == "member"


def test_disabled_members_are_not_listed(conn, maria, tom, groceries):
    lists.add_member(conn, groceries, tom["id"])
    users.set_disabled(conn, tom["id"], True)
    assert snapshot.list_view(conn, groceries, maria["id"])["members"] == ["maria"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_tasks.py -v`
Expected: FAIL, `ImportError: cannot import name 'snapshot'`.

- [ ] **Step 3: Write `taskly/tasks.py`**

```python
"""Queries on tasks. IDs are UUIDs made by the device, so creating is safe to retry.
Every function takes an open connection and returns plain dicts (done as a bool, people by name)."""

import sqlite3

SELECT = """SELECT t.id, t.list_id, t.title, t.done, c.username AS created_by, d.username AS done_by,
                   t.created_at, t.updated_at
            FROM tasks t
            LEFT JOIN users c ON c.id = t.created_by
            LEFT JOIN users d ON d.id = t.done_by"""


def _to_dict(row: sqlite3.Row) -> dict:
    task = dict(row)
    task["done"] = bool(task["done"])
    return task


def get_task(conn: sqlite3.Connection, task_id: str) -> dict | None:
    row = conn.execute(f"{SELECT} WHERE t.id = ?", (task_id,)).fetchone()
    return _to_dict(row) if row else None


def list_tasks(conn: sqlite3.Connection, list_id: str) -> list[dict]:
    # Open ones first, then newest first; rowid breaks ties within the same second.
    rows = conn.execute(f"{SELECT} WHERE t.list_id = ? ORDER BY t.done, t.created_at DESC, t.rowid DESC", (list_id,))
    return [_to_dict(row) for row in rows]


def create_task(conn: sqlite3.Connection, task_id: str, list_id: str, title: str, user_id: int) -> tuple[dict, bool]:
    """(task, created). If the id exists already (a device retrying), the stored task, unchanged."""
    try:
        with conn:
            conn.execute(
                "INSERT INTO tasks (id, list_id, title, created_by) VALUES (?, ?, ?, ?)",
                (task_id, list_id, title, user_id),
            )
    except sqlite3.IntegrityError:
        existing = get_task(conn, task_id)
        if existing is None:  # not a duplicate id: the list vanished meanwhile
            raise
        return existing, False
    return get_task(conn, task_id), True


def update_task(conn: sqlite3.Connection, task_id: str, user_id: int, *, title: str | None = None,
                done: bool | None = None) -> dict | None:
    """Changes only the fields given; ticking records who did it. None if there is no such task."""
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
                f"UPDATE tasks SET {assignments}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (*changes.values(), task_id),
            )
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    with conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0
```

- [ ] **Step 4: Write `taskly/snapshot.py`**

```python
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
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_tasks.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add taskly/tasks.py taskly/snapshot.py tests/test_tasks.py
git commit -m "feat: task queries and the per-user snapshot"
```

---

### Task 4: List, task and sync endpoints with permissions

**Files:**
- Modify: `taskly/routes.py` (rewrite)
- Delete: `taskly/todos.py`
- Modify: `tests/test_api.py` (replace the todo tests), `tests/conftest.py` (helpers)
- Create: `tests/test_permissions.py`

**Interfaces:**
- Consumes: `lists.*`, `tasks.*`, `snapshot.*`, `users.find_user`, `auth.CurrentUser`, `deps.Conn`.
- Produces endpoints (all need a login):
  - `GET /api/sync` → `snapshot.snapshot(...)`.
  - `POST /api/lists {name}` → 201 `list_view`; `PATCH /api/lists/{id} {name}` (owner) → `list_view`; `DELETE /api/lists/{id}` (owner) → 204.
  - `POST /api/lists/{id}/members {username}` (owner) → 201 (added) or 200 (already a member) with `list_view`; 404 `"No such user"` for unknown or disabled names.
  - `DELETE /api/lists/{id}/members/{username}` (owner; or that member themselves) → 204; 404 `"Not a member"`; the owner removing themselves → 409.
  - `POST /api/tasks {id: UUID, list_id: UUID, title}` → 201, or 200 for the same id in the same list, 409 for the same id in another list.
  - `PATCH /api/tasks/{id} {title?, done?}` → the task; `DELETE /api/tasks/{id}` → 204. 404 when gone or not a member.
- Produces (`tests/conftest.py`): `new_list(client, name="Groceries") -> dict`, `new_task(client, list_id, title="Milk") -> dict`.

- [ ] **Step 1: Test helpers**

`tests/conftest.py`, add:

```python
import uuid


def new_list(client, name="Groceries") -> dict:
    response = client.post("/api/lists", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def new_task(client, list_id, title="Milk") -> dict:
    response = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": list_id, "title": title})
    assert response.status_code == 201, response.text
    return response.json()
```

- [ ] **Step 2: Replace `tests/test_api.py`**

Remove the skip marker and every todo test (`add`, `test_starts_empty`, `test_create_returns_the_todo`, `test_blank_or_too_long_title_is_rejected`, `test_list_puts_open_todos_first_then_newest`, `test_patch_changes_only_given_fields`, `test_patch_unknown_todo_is_404`, `test_delete`, `test_todos_record_who_added_and_who_ticked`, `test_todos_need_a_login`, `test_todos_survive_a_restart`). Keep `test_health`, `test_page_and_its_files_are_served` and `test_api_runs_without_a_built_page`. Add:

```python
import uuid

from conftest import add_user, login, make_settings, new_list, new_task


def sync(client):
    response = client.get("/api/sync")
    assert response.status_code == 200
    return response.json()


def test_a_new_user_sees_no_lists(client):
    assert sync(client) == {"me": "maria", "lists": []}


def test_create_list(client):
    made = new_list(client, "  Groceries  ")
    assert (made["name"], made["owner"], made["role"], made["members"]) == ("Groceries", "maria", "owner", ["maria"])
    assert [l["name"] for l in sync(client)["lists"]] == ["Groceries"]


def test_list_names_are_checked(client):
    assert client.post("/api/lists", json={"name": "  "}).status_code == 422
    assert client.post("/api/lists", json={"name": "x" * 101}).status_code == 422


def test_rename_and_delete_list(client):
    made = new_list(client)
    new_task(client, made["id"])
    assert client.patch(f"/api/lists/{made['id']}", json={"name": "Food"}).json()["name"] == "Food"
    assert client.delete(f"/api/lists/{made['id']}").status_code == 204
    assert sync(client)["lists"] == []
    assert client.delete(f"/api/lists/{made['id']}").status_code == 404


def test_adding_members(client, settings):
    add_user(settings, "tom")
    add_user(settings, "ann")
    made = new_list(client)
    url = f"/api/lists/{made['id']}/members"

    first = client.post(url, json={"username": "TOM"})
    assert first.status_code == 201
    assert first.json()["members"] == ["maria", "tom"]
    assert client.post(url, json={"username": "tom"}).status_code == 200
    assert client.post(url, json={"username": "nobody"}).status_code == 404

    from contextlib import closing
    from taskly import db, users
    with closing(db.connect(settings.db_path)) as conn:
        users.set_disabled(conn, users.find_user(conn, "ann")["id"], True)
    assert client.post(url, json={"username": "ann"}).json()["detail"] == "No such user"


def test_leaving_and_removing(app, client, settings):
    add_user(settings, "tom")
    made = new_list(client)
    client.post(f"/api/lists/{made['id']}/members", json={"username": "tom"})

    assert client.delete(f"/api/lists/{made['id']}/members/maria").status_code == 409
    with TestClient(app) as tom:
        login(tom, "tom")
        assert tom.delete(f"/api/lists/{made['id']}/members/tom").status_code == 204
        assert sync(tom)["lists"] == []
        assert tom.patch(f"/api/tasks/{uuid.uuid4()}", json={"done": True}).status_code == 404
    assert client.delete(f"/api/lists/{made['id']}/members/tom").status_code == 404


def test_removed_members_lose_access_at_once(app, client, settings):
    add_user(settings, "tom")
    made = new_list(client)
    task = new_task(client, made["id"])
    client.post(f"/api/lists/{made['id']}/members", json={"username": "tom"})
    with TestClient(app) as tom:
        login(tom, "tom")
        assert tom.patch(f"/api/tasks/{task['id']}", json={"done": True}).status_code == 200
        assert client.delete(f"/api/lists/{made['id']}/members/tom").status_code == 204
        assert tom.patch(f"/api/tasks/{task['id']}", json={"done": False}).status_code == 404
        assert sync(tom)["lists"] == []


def test_create_task(client):
    made = new_list(client)
    task_id = str(uuid.uuid4())
    response = client.post("/api/tasks", json={"id": task_id, "list_id": made["id"], "title": "  Milk "})
    assert response.status_code == 201
    task = response.json()
    assert (task["id"], task["list_id"], task["title"], task["done"]) == (task_id, made["id"], "Milk", False)
    assert (task["created_by"], task["done_by"]) == ("maria", None)


def test_a_retried_create_changes_nothing(client):
    made = new_list(client)
    task = new_task(client, made["id"], "Milk")
    again = client.post("/api/tasks", json={"id": task["id"], "list_id": made["id"], "title": "Oat milk"})
    assert again.status_code == 200
    assert again.json()["title"] == "Milk"
    assert len(sync(client)["lists"][0]["tasks"]) == 1


def test_the_same_id_in_another_list_is_a_conflict(client):
    first, second = new_list(client, "A"), new_list(client, "B")
    task = new_task(client, first["id"])
    clash = client.post("/api/tasks", json={"id": task["id"], "list_id": second["id"], "title": "x"})
    assert clash.status_code == 409


def test_task_input_is_checked(client):
    made = new_list(client)
    assert client.post("/api/tasks", json={"id": "7", "list_id": made["id"], "title": "x"}).status_code == 422
    assert client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": " "}).status_code == 422
    assert client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": made["id"], "title": "x" * 501}).status_code == 422
    unknown_list = client.post("/api/tasks", json={"id": str(uuid.uuid4()), "list_id": str(uuid.uuid4()), "title": "x"})
    assert unknown_list.status_code == 404


def test_update_and_delete_task(client):
    made = new_list(client)
    task = new_task(client, made["id"])
    done = client.patch(f"/api/tasks/{task['id']}", json={"done": True}).json()
    assert (done["done"], done["done_by"], done["title"]) == (True, "maria", "Milk")
    assert client.patch(f"/api/tasks/{task['id']}", json={"title": "Oat milk"}).json()["done"] is True
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert client.patch(f"/api/tasks/{task['id']}", json={"done": False}).status_code == 404


def test_sync_sorts_lists_by_name_and_tasks_open_first(client):
    new_list(client, "zoo")
    food = new_list(client, "Food")
    first = new_task(client, food["id"], "first")
    new_task(client, food["id"], "second")
    client.patch(f"/api/tasks/{first['id']}", json={"done": True})
    seen = sync(client)
    assert [l["name"] for l in seen["lists"]] == ["Food", "zoo"]
    assert [t["title"] for t in seen["lists"][0]["tasks"]] == ["second", "first"]


def test_lists_survive_a_restart(settings):
    add_user(settings, "maria")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        new_task(client, new_list(client)["id"], "still here")
    with TestClient(create_app(settings)) as client:
        login(client, "maria")
        assert [t["title"] for t in sync(client)["lists"][0]["tasks"]] == ["still here"]
```

- [ ] **Step 3: Write the permission table**

`tests/test_permissions.py`:

```python
"""Who may do what: every list and task endpoint, for the owner, a member, someone outside
the list, and someone not logged in."""

import uuid
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from conftest import add_user, login, new_list, new_task

ROLES = ["owner", "member", "outsider", "anonymous"]

# (name, method, path, body, expected status per role). {list} and {task} are filled in.
CASES = [
    ("sync", "GET", "/api/sync", None, {"owner": 200, "member": 200, "outsider": 200, "anonymous": 401}),
    ("rename list", "PATCH", "/api/lists/{list}", {"name": "Food"}, {"owner": 200, "member": 403, "outsider": 404, "anonymous": 401}),
    ("delete list", "DELETE", "/api/lists/{list}", None, {"owner": 204, "member": 403, "outsider": 404, "anonymous": 401}),
    ("add member", "POST", "/api/lists/{list}/members", {"username": "bob"}, {"owner": 201, "member": 403, "outsider": 404, "anonymous": 401}),
    ("remove zoe", "DELETE", "/api/lists/{list}/members/zoe", None, {"owner": 204, "member": 403, "outsider": 404, "anonymous": 401}),
    ("create task", "POST", "/api/tasks", {"id": "{new}", "list_id": "{list}", "title": "x"}, {"owner": 201, "member": 201, "outsider": 404, "anonymous": 401}),
    ("tick task", "PATCH", "/api/tasks/{task}", {"done": True}, {"owner": 200, "member": 200, "outsider": 404, "anonymous": 401}),
    ("delete task", "DELETE", "/api/tasks/{task}", None, {"owner": 204, "member": 204, "outsider": 404, "anonymous": 401}),
]


@pytest.fixture
def world(app, settings):
    """maria owns Groceries with tom and zoe as members and one task; ann is in no list; bob exists."""
    for name in ["maria", "tom", "zoe", "ann", "bob"]:
        add_user(settings, name)
    with ExitStack() as stack:
        clients = {}
        for role, name in [("owner", "maria"), ("member", "tom"), ("outsider", "ann")]:
            clients[role] = stack.enter_context(TestClient(app))
            login(clients[role], name)
        clients["anonymous"] = stack.enter_context(TestClient(app))
        groceries = new_list(clients["owner"])
        for name in ["tom", "zoe"]:
            clients["owner"].post(f"/api/lists/{groceries['id']}/members", json={"username": name})
        task = new_task(clients["owner"], groceries["id"])
        yield clients, {"list": groceries["id"], "task": task["id"]}


def fill(value, ids):
    if isinstance(value, dict):
        return {k: fill(v, ids) for k, v in value.items()}
    if isinstance(value, str):
        return value.format(new=str(uuid.uuid4()), **ids)
    return value


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("name, method, path, body, expected", CASES, ids=[c[0] for c in CASES])
def test_permissions(world, role, name, method, path, body, expected):
    clients, ids = world
    response = clients[role].request(method, fill(path, ids), json=fill(body, ids))
    assert response.status_code == expected[role], response.text


def test_outsiders_see_nothing_in_sync(world):
    clients, _ = world
    assert clients["outsider"].get("/api/sync").json() == {"me": "ann", "lists": []}
```

- [ ] **Step 4: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_permissions.py -q`
Expected: FAIL, 404s from `POST /api/lists` in the helpers.

- [ ] **Step 5: Rewrite `taskly/routes.py`**

```python
"""The data endpoints: lists, their members, tasks, and GET /api/sync.

Every list or task action first asks the user's role in the list: none is a 404 (as if it
didn't exist, so ids can't be probed), a member doing an owner's action is a 403."""

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
    lists.rename_list(conn, str(list_id), body.name)
    return snapshot.list_view(conn, str(list_id), user["id"])


@router.delete("/api/lists/{list_id}", status_code=204)
def delete_list(list_id: UUID, user: CurrentUser, conn: Conn) -> None:
    require_role(conn, str(list_id), user, owner=True)
    lists.delete_list(conn, str(list_id))


@router.post("/api/lists/{list_id}/members")
def add_member(list_id: UUID, body: MemberBody, response: Response, user: CurrentUser, conn: Conn) -> dict:
    require_role(conn, str(list_id), user, owner=True)
    member = users.find_user(conn, body.username.strip())
    if member is None or member["disabled_at"]:
        raise HTTPException(status_code=404, detail="No such user")
    response.status_code = 201 if lists.add_member(conn, str(list_id), member["id"]) else 200
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
    task, created = tasks.create_task(conn, str(body.id), str(body.list_id), body.title, user["id"])
    if task["list_id"] != str(body.list_id):
        raise HTTPException(status_code=409, detail="That task id is already used")
    # 200 for a retry: the device sent this create before but never got the answer.
    response.status_code = 201 if created else 200
    return task


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskUpdate, user: CurrentUser, conn: Conn) -> dict:
    task_for(conn, task_id, user)
    return tasks.update_task(conn, str(task_id), user["id"], title=body.title, done=body.done)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, user: CurrentUser, conn: Conn) -> None:
    task_for(conn, task_id, user)
    tasks.delete_task(conn, str(task_id))
```

Then `git rm taskly/todos.py`.

- [ ] **Step 6: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (the permission table is 36 tests).

- [ ] **Step 7: Commit**

```bash
git add taskly/routes.py tests/test_api.py tests/test_permissions.py tests/conftest.py
git commit -m "feat: list, member, task and sync endpoints; /api/todos is gone"
```

---

### Task 5: The admin command knows about lists

**Files:**
- Modify: `taskly/admin.py`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `lists.claim_unowned`, `lists.hand_over`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin.py`:

```python
from taskly import lists


def test_the_first_account_claims_the_old_list(settings, capsys):
    db.migrate(settings.db_path)
    with open_db(settings) as conn, conn:
        conn.execute("INSERT INTO lists (id, name) VALUES ('legacy', 'Taskly')")
    assert run(settings, "add-user", "maria", prompt=answers(PASSWORD, PASSWORD)) == 0
    assert "Now owns: Taskly" in capsys.readouterr().out
    with open_db(settings) as conn:
        maria = users.find_user(conn, "maria")
        assert lists.role(conn, "legacy", maria["id"]) == "owner"


def test_disabling_an_owner_hands_their_lists_over(settings, capsys):
    maria, tom = add_user(settings, "maria"), add_user(settings, "tom")
    with open_db(settings) as conn:
        list_id = lists.create_list(conn, "Groceries", maria["id"])
        lists.add_member(conn, list_id, tom["id"])
    assert run(settings, "disable-user", "maria") == 0
    assert "Groceries now belongs to tom" in capsys.readouterr().out
    with open_db(settings) as conn:
        assert lists.role(conn, list_id, tom["id"]) == "owner"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin.py -v`
Expected: the two new tests FAIL on the printed text.

- [ ] **Step 3: Update `taskly/admin.py`**

`from . import db, lists, sessions, users`, and replace the two `# Phase 2: …` comments:

In `add_user`:

```python
    claimed = lists.claim_unowned(conn, user["id"])
    if claimed:
        print(f"Now owns: {', '.join(claimed)}")
```

In `disable_user`, before `users.set_disabled(...)`:

```python
    for name, heir in lists.hand_over(conn, user["id"]):
        print(f"{name} now belongs to {heir}.")
```

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add taskly/admin.py tests/test_admin.py
git commit -m "feat: new accounts claim the old list; disabled owners hand theirs over"
```

---

### Task 6: The page: list picker, new list, list settings

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/style.css`
- Create: `frontend/src/ListsPage.tsx`, `frontend/src/Tasks.tsx`, `frontend/src/TaskItem.tsx`, `frontend/src/ListPicker.tsx`, `frontend/src/NewList.tsx`, `frontend/src/ListSettings.tsx`, `frontend/src/pickList.ts`
- Delete: `frontend/src/TodoPage.tsx`, `frontend/src/TodoItem.tsx`
- Test: `frontend/src/pickList.test.ts`

**Interfaces:**
- Consumes: the endpoints of Task 4.
- Produces (`api.ts`), replacing `Todo`:

```ts
export type Task = {
  id: string; list_id: string; title: string; done: boolean;
  created_by: string | null; done_by: string | null; created_at: string; updated_at: string;
};
export type TaskList = { id: string; name: string; owner: string | null; role: "owner" | "member"; members: string[]; tasks: Task[] };
export type Snapshot = { me: string; lists: TaskList[] };
```

- Produces (`ListsPage.tsx`): `type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>` (undefined when the request failed; the error is shown); `ListsPage({ onLoggedOut })`. Phase 3 replaces how `ListsPage` gets its data but keeps `Change` for list actions.
- Produces (`pickList.ts`): `pickList(lists: { id: string }[], saved: string | null): string | null`, `savedList(): string | null`, `saveList(id: string): void` (localStorage key `taskly.list`; storage errors ignored).

- [ ] **Step 1: Write the failing test**

`frontend/src/pickList.test.ts`:

```ts
import { expect, test } from "vitest";
import { pickList } from "./pickList";

const lists = [{ id: "a" }, { id: "b" }];

test("the remembered list when it still exists", () => {
  expect(pickList(lists, "b")).toBe("b");
});

test("the first list when the remembered one is gone or there is none", () => {
  expect(pickList(lists, "deleted")).toBe("a");
  expect(pickList(lists, null)).toBe("a");
});

test("nothing when there are no lists", () => {
  expect(pickList([], "a")).toBeNull();
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `Failed to resolve import "./pickList"`.

- [ ] **Step 3: `pickList.ts`**

```ts
// Which list to show: the one this device showed last, if it still exists, else the first.
const KEY = "taskly.list";

export function pickList(lists: { id: string }[], saved: string | null): string | null {
  if (saved && lists.some((list) => list.id === saved)) return saved;
  return lists[0]?.id ?? null;
}

// localStorage can throw (private windows, blocked storage): then nothing is remembered.
export function savedList(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveList(id: string): void {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // not remembered; harmless
  }
}
```

Run: `npm --prefix frontend test`
Expected: PASS.

- [ ] **Step 4: Types**

In `frontend/src/api.ts`, replace the `Todo` type with the three types in **Interfaces** above.

- [ ] **Step 5: The components**

`frontend/src/ListsPage.tsx`:

```tsx
// The lists: reads everything from /api/sync, and after every change reads it again,
// so the page always shows what the server has.
import { useEffect, useState } from "react";
import { api, type Snapshot } from "./api";
import { ListPicker } from "./ListPicker";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { pickList, savedList, saveList } from "./pickList";
import { Tasks } from "./Tasks";

export type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>;
type Panel = "none" | "new" | "settings";

export function ListsPage({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(savedList);
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);

  function fail(e: unknown) {
    if (isLoggedOut(e)) onLoggedOut();
    else setError((e as Error).message);
  }

  async function refresh() {
    try {
      setSnapshot(await api<Snapshot>("GET", "/api/sync"));
    } catch (e) {
      fail(e);
    }
  }

  async function change<T>(request: () => Promise<T>): Promise<T | undefined> {
    let result: T | undefined;
    try {
      result = await request();
      setError(null);
    } catch (e) {
      fail(e);
    }
    await refresh();
    return result;
  }

  useEffect(() => {
    void refresh();
  }, []);

  function choose(id: string) {
    setSelected(id);
    saveList(id);
    setPanel("none");
  }

  if (!snapshot) return <main>{error && <p className="error" role="alert">{error}</p>}</main>;

  const current = snapshot.lists.find((list) => list.id === pickList(snapshot.lists, selected));
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);

  return (
    <main>
      <ListPicker
        lists={snapshot.lists}
        current={current}
        onChoose={choose}
        onNew={() => toggle("new")}
        onSettings={() => toggle("settings")}
      />
      {panel === "new" && <NewList change={change} onCreated={choose} onCancel={() => setPanel("none")} />}
      {panel === "settings" && current && (
        <ListSettings list={current} me={snapshot.me} change={change} onClose={() => setPanel("none")} />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {current ? (
        <Tasks key={current.id} list={current} change={change} />
      ) : (
        <p className="empty">No lists yet. Make one with “New list”.</p>
      )}
    </main>
  );
}
```

`frontend/src/ListPicker.tsx`:

```tsx
// The row at the top: which list, its settings, and a new one.
import type { TaskList } from "./api";

type Props = {
  lists: TaskList[];
  current: TaskList | undefined;
  onChoose: (id: string) => void;
  onNew: () => void;
  onSettings: () => void;
};

export function ListPicker({ lists, current, onChoose, onNew, onSettings }: Props) {
  return (
    <div className="picker">
      {current ? (
        <select aria-label="list" value={current.id} onChange={(e) => onChoose(e.target.value)}>
          {lists.map((list) => <option key={list.id} value={list.id}>{list.name}</option>)}
        </select>
      ) : (
        <h1>Taskly</h1>
      )}
      {current && <button type="button" className="plain" onClick={onSettings}>Settings</button>}
      <button type="button" className="plain" onClick={onNew}>New list</button>
    </div>
  );
}
```

`frontend/src/NewList.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { api, type TaskList } from "./api";
import type { Change } from "./ListsPage";

export function NewList({ change, onCreated, onCancel }: { change: Change; onCreated: (id: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const created = await change(() => api<TaskList>("POST", "/api/lists", { name: trimmed }));
    if (created) onCreated(created.id);
  }

  return (
    <form className="panel row" onSubmit={submit} autoComplete="off">
      <input aria-label="new list name" placeholder="List name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required autoFocus />
      <button type="submit">Create</button>
      <button type="button" className="plain" onClick={onCancel}>Cancel</button>
    </form>
  );
}
```

`frontend/src/ListSettings.tsx`:

```tsx
// Owners rename, add and remove people, and delete. Members see who's in and can leave.
import { useState, type FormEvent } from "react";
import { api, type TaskList } from "./api";
import type { Change } from "./ListsPage";

type Props = { list: TaskList; me: string; change: Change; onClose: () => void };

export function ListSettings({ list, me, change, onClose }: Props) {
  const [name, setName] = useState(list.name);
  const [newMember, setNewMember] = useState("");
  const [confirming, setConfirming] = useState(false);
  const owner = list.role === "owner";
  const base = `/api/lists/${list.id}`;
  const member = (username: string) => `${base}/members/${encodeURIComponent(username)}`;

  function rename(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed && trimmed !== list.name) void change(() => api("PATCH", base, { name: trimmed }));
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    const username = newMember.trim();
    if (!username) return;
    if ((await change(() => api("POST", `${base}/members`, { username }))) !== undefined) setNewMember("");
  }

  async function deleteOrLeave() {
    const done = await change(() => api("DELETE", owner ? base : member(me)));
    if (done !== undefined) onClose();
  }

  return (
    <section className="panel stack">
      {owner ? (
        <form className="row" onSubmit={rename}>
          <input aria-label="list name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
          <button type="submit">Rename</button>
        </form>
      ) : (
        <p className="hint">{list.owner ? `${list.owner} owns this list.` : "Nobody owns this list."}</p>
      )}

      <div>
        <h2>People</h2>
        <ul className="members">
          {list.members.map((username) => (
            <li key={username}>
              <span>{username}{username === list.owner && " (owner)"}</span>
              {owner && username !== list.owner && (
                <button type="button" className="delete" aria-label={`remove ${username}`} onClick={() => void change(() => api("DELETE", member(username)))}>
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
        {owner && (
          <form className="row" onSubmit={add} autoComplete="off">
            <input aria-label="username to add" placeholder="Username" value={newMember} onChange={(e) => setNewMember(e.target.value)} autoCapitalize="none" />
            <button type="submit">Add</button>
          </form>
        )}
      </div>

      {confirming ? (
        <div className="row confirm">
          <span>{owner ? `Delete “${list.name}” and its ${list.tasks.length} tasks?` : `Leave “${list.name}”?`}</span>
          <button type="button" className="danger" onClick={deleteOrLeave}>{owner ? "Delete" : "Leave"}</button>
          <button type="button" className="plain" onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      ) : (
        <button type="button" className="plain danger-text" onClick={() => setConfirming(true)}>
          {owner ? "Delete list" : "Leave list"}
        </button>
      )}
    </section>
  );
}
```

`frontend/src/Tasks.tsx`:

```tsx
// One list's tasks: add a task (the device picks its id), then the tasks themselves.
import { useRef, useState, type FormEvent } from "react";
import { api, type TaskList } from "./api";
import type { Change } from "./ListsPage";
import { TaskItem } from "./TaskItem";

export function Tasks({ list, change }: { list: TaskList; change: Change }) {
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    await change(() => api("POST", "/api/tasks", { id: crypto.randomUUID(), list_id: list.id, title: trimmed }));
    setTitle("");
    titleInput.current?.focus();
  }

  return (
    <>
      <form onSubmit={add} autoComplete="off">
        <input ref={titleInput} name="title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={500} placeholder="What needs doing?" required />
        <button type="submit">Add</button>
      </form>
      <ul>
        {list.tasks.map((task) => <TaskItem key={task.id} task={task} change={change} />)}
      </ul>
      {list.tasks.length === 0 && <p className="empty">Nothing to do. Add something above.</p>}
    </>
  );
}
```

`frontend/src/TaskItem.tsx`: `git mv frontend/src/TodoItem.tsx frontend/src/TaskItem.tsx`, then in it:
- rename the component to `TaskItem`, the prop `todo` to `task` (type `Task` from `./api`), and `import type { Change } from "./ListsPage";`
- `const path = \`/api/tasks/${task.id}\`;`
- keep everything else (rename behaviour, attribution line) as it is.

`frontend/src/App.tsx`: import and render `ListsPage` instead of `TodoPage`. Then `git rm frontend/src/TodoPage.tsx`.

`frontend/src/style.css`, append:

```css
.picker { display: flex; align-items: center; gap: 4px; margin-bottom: 16px; }
.picker select, .picker h1 { margin: 0 auto 0 0; }
.picker select {
  max-width: 60%;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--card);
  color: var(--text);
  font-family: inherit;
  font-size: 20px;
  font-weight: 600;
}
.panel input { flex: 1; min-width: 0; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); color: var(--text); font: inherit; }
h2 { margin: 0 0 8px; font-size: 16px; }
ul.members { margin: 0 0 8px; }
ul.members li { padding: 4px 0; margin: 0; border: 0; background: none; justify-content: space-between; }
.confirm { align-items: center; flex-wrap: wrap; }
button.danger { background: var(--danger); }
button.danger-text { color: var(--danger); align-self: flex-start; }
```

- [ ] **Step 6: Typecheck, test, build**

Run: `npm --prefix frontend run build` and `npm --prefix frontend test`
Expected: no type errors, all tests pass.

- [ ] **Step 7: Check it in the browser, like a user**

Migrate your local database first (starting uvicorn does it) and create a second account (`.venv\Scripts\python.exe -m taskly.admin add-user tom`). With uvicorn and `npm --prefix frontend run dev` running, at <http://localhost:5173/>:
- Logged in as your account: the old todos are in a list "Taskly", with "added by" kept.
- New list "Groceries": it's selected. Add "Milk", tick it, rename it.
- Settings: rename to "Food"; add `tom`; add `nobody` → "No such user", the field keeps the name.
- In a private window, log in as tom: "Food" is there; Settings shows "maria owns this list." and "Leave list". Tick a task as tom; back as yourself, reload: "done by tom".
- As tom: Leave → the list disappears for tom.
- As yourself: Delete list → confirm text names the task count → the next list shows. Reload: the page remembers the last list you picked; after deleting it, it falls back to the first one.
- Phone width: the picker row fits, no horizontal scroll. Console: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: named lists on the page: picker, new list, settings"
```

---

### Task 7: README and CLAUDE.md

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: README, "## API"**

Replace the todo rows of the table with:

```markdown
| `GET /api/sync` | | Everything you can see: `{"me", "lists": [{"id", "name", "owner", "role", "members", "tasks": [...]}]}`, lists by name, tasks open first then newest |
| `POST /api/lists` | `{"name": "Groceries"}` | 201 and the list; you own it |
| `PATCH /api/lists/{id}` | `{"name": ...}` | The list. Owner only |
| `DELETE /api/lists/{id}` | | 204; its tasks go too. Owner only |
| `POST /api/lists/{id}/members` | `{"username": "tom"}` | 201 (200 if already in). Owner only; 404 for unknown users |
| `DELETE /api/lists/{id}/members/{username}` | | 204. The owner removes anyone; anyone can remove themselves (leave), except the owner (409) |
| `POST /api/tasks` | `{"id": "<uuid>", "list_id": "<uuid>", "title": "Milk"}` | 201 and the task. The same `id` again in the same list: 200 and the stored task (a safe retry) |
| `PATCH /api/tasks/{id}` | `{"title": ...}` and/or `{"done": true}` | The task |
| `DELETE /api/tasks/{id}` | | 204 |
```

and replace the paragraph describing a todo with:

```markdown
A task is `{"id", "list_id", "title", "done", "created_by", "done_by",
"created_at", "updated_at"}`: people by username (`null` for tasks from before
accounts), times in UTC set by the server (`2026-09-28T12:00:00Z`). Task ids are
UUIDs the page makes itself. Titles are trimmed and 1–500 characters, list names
1–100 (422 otherwise). Anything in a list you're not in answers 404, as if it
didn't exist; an owner's action by a member answers 403. Interactive docs are at
`/docs`.
```

- [ ] **Step 2: README, "Layout" and "Accounts"**

In the Layout block replace `todos.py      the queries` with:

```
  users.py, sessions.py, passwords.py   accounts
  lists.py, tasks.py                    lists, members and tasks
  snapshot.py   what a user can see (GET /api/sync)
  auth.py       logins, the session cookie, the /api account endpoints
  admin.py      python -m taskly.admin: accounts from the command line
```

In "Accounts", after the table, add: `The first account created after phase 2 takes over the old list "Taskly" if it has no owner yet. Disabling someone hands each list they own to the member who joined it earliest.`

- [ ] **Step 3: CLAUDE.md**

In "## Architecture", replace the **Queries** bullet with:

```markdown
- **Queries** live in `users.py`, `sessions.py`, `lists.py`, `tasks.py` and `snapshot.py` and return plain dicts (`done` as a bool, people as usernames). Routes stay thin: validate with pydantic (`Title`, `ListName` strip and bound length; ids are `UUID`), check the role with `require_role`/`task_for` (none → 404, member doing an owner's action → 403), call the queries.
- **Lists.** Every list has an owner, who is also a member row. `GET /api/sync` is the only read endpoint for lists and tasks. Task ids are UUIDs made by the page; `POST /api/tasks` with an existing id in the same list is a retry and answers 200 unchanged.
```

In the **Frontend** bullet, replace "After every change the page reloads the list from the server" with "After every change the page reloads `/api/sync`".

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: named lists, members and the new API"
```

---

### Task 8: Deploy phase 2

- [ ] **Step 1:** Merge `phase-2` into `main`; both test suites pass on `main`.
- [ ] **Step 2:** `.\scripts\deploy.ps1`. Expected: `backed up to …`, `schema 2 -> 3`, `Deployed. status=ok`. (For a few seconds between the migration and the new app starting, the old app can't find `todos`: a request then errors, and a reload fixes it.)
- [ ] **Step 3:** On the VM: `docker compose exec app python -m taskly.admin list-users` to confirm everyone; open the site: "Taskly" holds the old todos for everyone.
- [ ] **Step 4:** On a phone: switch lists, create one, add someone.
