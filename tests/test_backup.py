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
        conn.execute("INSERT INTO todos (title) VALUES ('keep me')")

    target = backup.backup(path, now=datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc))

    assert target == tmp_path / "backups" / "taskly-20260928T120000Z.db"
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT title FROM todos").fetchall() == [("keep me",)]
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
