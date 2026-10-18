import re
import sqlite3
from contextlib import closing

from taskly import db


def test_migrate_creates_the_file_and_folder(tmp_path):
    path = tmp_path / "nested" / "taskly.db"
    assert db.migrate(str(path)) == len(db.MIGRATIONS)
    assert path.exists()


def test_migrate_twice_changes_nothing(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('keep', 'x')")
    assert db.migrate(path) == len(db.MIGRATIONS)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT username FROM users").fetchall() == [("keep",)]


def test_migrate_runs_only_new_migrations(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "CREATE TABLE extra (id INTEGER);"])
    assert db.migrate(path) == len(db.MIGRATIONS)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchone() is not None


def test_a_failed_migration_leaves_the_version_alone(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    version = db.migrate(path)
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "CREATE TABLE extra (id INTEGER); NOT SQL;"])
    try:
        db.migrate(path)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("a broken migration should raise")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchone() is None


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

    migrate_to(path, 3, monkeypatch)  # exactly 3: migration 5 turns done into status

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


def test_migration_5_turns_done_into_a_status(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 4, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            INSERT INTO users (username, password_hash) VALUES ('maria', 'x');
            INSERT INTO lists (id, name, owner_id) VALUES ('l1', 'Food', 1);
            INSERT INTO tasks (id, list_id, title, done, done_by, updated_at) VALUES
                ('t1', 'l1', 'Milk', 1, 1, '2026-01-02T00:00:00Z'),
                ('t2', 'l1', 'Eggs', 0, NULL, '2026-01-03T00:00:00Z');
        """)

    assert db.migrate(path) == len(db.MIGRATIONS)

    assert rows(path, "SELECT id, status, done_by, updated_at FROM tasks ORDER BY id") == [
        {"id": "t1", "status": "done", "done_by": 1, "updated_at": "2026-01-02T00:00:00Z"},
        {"id": "t2", "status": "new", "done_by": None, "updated_at": "2026-01-03T00:00:00Z"},
    ]
    assert "done" not in [c["name"] for c in rows(path, "PRAGMA table_info(tasks)")]
    with sqlite3.connect(path) as conn:
        try:
            conn.execute("UPDATE tasks SET status = 'later' WHERE id = 't1'")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("status must be new, progress or done")


def test_migration_6_adds_an_empty_due_date(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 5, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            INSERT INTO users (username, password_hash) VALUES ('maria', 'x');
            INSERT INTO lists (id, name, owner_id) VALUES ('l1', 'Food', 1);
            INSERT INTO tasks (id, list_id, title, status) VALUES ('t1', 'l1', 'Milk', 'progress');
        """)

    assert db.migrate(path) == len(db.MIGRATIONS)

    assert rows(path, "SELECT id, status, due_date FROM tasks") == [{"id": "t1", "status": "progress", "due_date": None}]
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE tasks SET due_date = '2026-10-17' WHERE id = 't1'")
        for wrong in ["2026-02-30", "2026-10-17 09:00", "tomorrow"]:
            try:
                conn.execute("UPDATE tasks SET due_date = ? WHERE id = 't1'", (wrong,))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError(f"{wrong!r} isn't a calendar day")
    assert rows(path, "SELECT due_date FROM tasks") == [{"due_date": "2026-10-17"}]


def test_migration_7_adds_a_time_that_needs_a_date_and_a_zone(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 6, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            INSERT INTO users (username, password_hash) VALUES ('maria', 'x');
            INSERT INTO lists (id, name, owner_id) VALUES ('l1', 'Food', 1);
            INSERT INTO tasks (id, list_id, title, due_date) VALUES ('t1', 'l1', 'Milk', '2026-10-17'), ('t2', 'l1', 'Eggs', NULL);
        """)

    assert db.migrate(path) == len(db.MIGRATIONS)

    assert rows(path, "SELECT id, due_date, due_time, due_zone FROM tasks ORDER BY id") == [
        {"id": "t1", "due_date": "2026-10-17", "due_time": None, "due_zone": None},
        {"id": "t2", "due_date": None, "due_time": None, "due_zone": None},
    ]
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE tasks SET due_time = '15:00', due_zone = 'America/New_York' WHERE id = 't1'")
        for task, time, zone in [("t2", "15:00", "UTC"), ("t1", "24:00", "UTC"), ("t1", "9:00", "UTC"),
                                 ("t1", "15:00", None), ("t1", None, "UTC")]:
            try:
                conn.execute("UPDATE tasks SET due_time = ?, due_zone = ? WHERE id = ?", (time, zone, task))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError(f"{task}: {time!r} in {zone!r} should be refused")
        try:
            conn.execute("UPDATE tasks SET due_date = NULL WHERE id = 't1'")  # a time without its date
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("a time needs its date")
    assert rows(path, "SELECT due_time, due_zone FROM tasks WHERE id = 't1'") == [{"due_time": "15:00", "due_zone": "America/New_York"}]


def test_migration_8_adds_empty_notes(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    migrate_to(path, 7, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            INSERT INTO users (username, password_hash) VALUES ('maria', 'x');
            INSERT INTO lists (id, name, owner_id) VALUES ('l1', 'Food', 1);
            INSERT INTO tasks (id, list_id, title, due_date) VALUES ('t1', 'l1', 'Milk', '2026-10-17');
        """)

    assert db.migrate(path) == len(db.MIGRATIONS)

    assert rows(path, "SELECT id, due_date, notes FROM tasks") == [{"id": "t1", "due_date": "2026-10-17", "notes": None}]
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE tasks SET notes = 'The oat one\nhttps://example.com' WHERE id = 't1'")
        try:
            conn.execute("UPDATE tasks SET notes = '' WHERE id = 't1'")  # no note is NULL, never ''
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("an empty note should be refused")
    assert rows(path, "SELECT notes FROM tasks") == [{"notes": "The oat one\nhttps://example.com"}]


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
