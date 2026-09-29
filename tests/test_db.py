import sqlite3

from taskly import db


def test_migrate_creates_the_file_and_folder(tmp_path):
    path = tmp_path / "nested" / "taskly.db"
    assert db.migrate(str(path)) == len(db.MIGRATIONS)
    assert path.exists()


def test_migrate_twice_changes_nothing(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO todos (title) VALUES ('keep me')")
    assert db.migrate(path) == len(db.MIGRATIONS)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT title FROM todos").fetchall() == [("keep me",)]


def test_migrate_runs_only_new_migrations(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "ALTER TABLE todos ADD COLUMN note TEXT;"])
    assert db.migrate(path) == len(db.MIGRATIONS)
    with sqlite3.connect(path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(todos)")]
    assert "note" in columns


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
