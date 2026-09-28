"""`python -m taskly.backup`: copy the database into backups/ next to it; keep the newest ten.

deploy.ps1 runs it before migrating. SQLite's backup API makes a consistent copy while the app runs."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .settings import Settings

KEEP = 10


def backup(path: str, keep: int = KEEP, now: datetime | None = None) -> Path | None:
    source = Path(path)
    if not source.exists():
        return None
    folder = source.parent / "backups"
    folder.mkdir(exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{source.stem}-{stamp}.db"
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    # The names sort by time, oldest first.
    for old in sorted(folder.glob(f"{source.stem}-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    target = backup(Settings().db_path)
    print(f"backed up to {target}" if target else "no database yet, nothing to back up")


if __name__ == "__main__":
    main()
