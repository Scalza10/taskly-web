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
