import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from taskly import backup, db


def test_no_database_means_nothing_to_back_up(tmp_path):
    assert backup.backup(str(tmp_path / "taskly.db")) is None
    assert not (tmp_path / "backups").exists()


def test_backup_is_a_full_copy(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('keep me', 'x')")

    target = backup.backup(path, now=datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc))

    assert target == tmp_path / "backups" / "taskly-20260928T120000Z.db"
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT username FROM users").fetchall() == [("keep me",)]
        assert copy.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)


def test_only_the_newest_backups_are_kept(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for day in range(12):
        backup.backup(path, keep=10, now=start + timedelta(days=day))

    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(names) == 10
    assert names[0] == "taskly-20260103T000000Z.db"
    assert names[-1] == "taskly-20260112T000000Z.db"


def _one_migration_behind(path, monkeypatch):
    db.migrate(path)
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "CREATE TABLE extra (id INTEGER);"])


def test_backup_before_a_migration_is_named_for_it_and_is_a_full_copy(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('keep me', 'x')")
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "CREATE TABLE extra (id INTEGER);"])

    target = backup.backup(path, now=datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc))

    n = len(db.MIGRATIONS)
    assert target == tmp_path / "backups" / f"taskly-20260928T120000Z-before-schema-{n}.db"
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT username FROM users").fetchall() == [("keep me",)]
        assert copy.execute("PRAGMA user_version").fetchone()[0] == n - 1


def test_kept_backups_survive_the_rotation(tmp_path, monkeypatch):
    path = str(tmp_path / "taskly.db")
    _one_migration_behind(path, monkeypatch)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    kept = backup.backup(path, now=start)
    db.migrate(path)
    for day in range(1, 13):
        backup.backup(path, keep=10, now=start + timedelta(days=day))

    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert kept.exists()
    assert len(names) == 11
    assert sum("before-schema" in name for name in names) == 1
    assert "taskly-20260104T000000Z.db" in names
    assert "taskly-20260103T000000Z.db" not in names


def test_an_up_to_date_database_gets_an_ordinary_name(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    target = backup.backup(path, now=datetime(2026, 9, 28, tzinfo=timezone.utc))
    assert "before-schema" not in target.name
