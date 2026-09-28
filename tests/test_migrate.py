from taskly import db, migrate


def test_first_run_creates_the_schema(tmp_path):
    path = str(tmp_path / "taskly.db")
    assert db.current_version(path) == 0
    assert migrate.run(path) == f"schema 0 -> {len(db.MIGRATIONS)}"


def test_second_run_has_nothing_to_do(tmp_path):
    path = str(tmp_path / "taskly.db")
    migrate.run(path)
    assert migrate.run(path) == f"schema {len(db.MIGRATIONS)}, nothing to do"


def test_current_version_does_not_create_the_file(tmp_path):
    path = tmp_path / "taskly.db"
    assert db.current_version(str(path)) == 0
    assert not path.exists()
