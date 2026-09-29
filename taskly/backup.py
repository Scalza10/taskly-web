"""`python -m taskly.backup`: copy the database into backups/ next to it; keep the newest ten.

A backup taken while a migration is pending is named `...-before-schema-<N>.db` and is never rotated away.

deploy.ps1 runs it before migrating. SQLite's backup API makes a consistent copy while the app runs."""

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .settings import Settings

KEEP = 10


def backup(path: str, keep: int = KEEP, now: datetime | None = None) -> Path | None:
    source = Path(path)
    if not source.exists():
        return None
    folder = source.parent / "backups"
    folder.mkdir(exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    # Backup runs from the new image, so a database behind db.MIGRATIONS is about to be migrated.
    pending = db.current_version(path) < len(db.MIGRATIONS)
    suffix = f"-before-schema-{len(db.MIGRATIONS)}" if pending else ""
    target = folder / f"{source.stem}-{stamp}{suffix}.db"
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    # Only ordinary backups rotate (kept ones have a suffix after the stamp). Names sort by time, oldest first.
    ordinary = re.compile(rf"{re.escape(source.stem)}-\d{{8}}T\d{{6}}Z\.db")
    for old in sorted(p for p in folder.iterdir() if ordinary.fullmatch(p.name))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    target = backup(Settings().db_path)
    if not target:
        print("no database yet, nothing to back up")
    elif "-before-schema-" in target.name:
        print(f"backed up to {target} (kept: a migration follows)")
    else:
        print(f"backed up to {target}")


if __name__ == "__main__":
    main()
