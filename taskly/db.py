"""SQLite storage: one file, its schema versioned with PRAGMA user_version."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

# Each entry takes the schema up one version, in order. Only ever append:
# a database that already ran an entry never runs it again, so editing one
# changes nothing on the VM.
MIGRATIONS = [
    """
    CREATE TABLE todos (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT    NOT NULL,
        done       INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    """,
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
]


def connect(path: str) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may open the connection in one worker
    # thread and use it in another, but a connection still serves one request.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def migrate(path: str) -> int:
    """Create the file if needed and apply any new migrations. Returns the schema version."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn:
        # WAL lets the page read while a write is in progress. It is stored in the file.
        conn.execute("PRAGMA journal_mode = WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            # One transaction per migration, version bump included, so a failed one leaves nothing half done.
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        return conn.execute("PRAGMA user_version").fetchone()[0]


def current_version(path: str) -> int:
    """The schema version of the file, 0 if there is no file yet. Never creates it."""
    if not Path(path).exists():
        return 0
    with closing(connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def session(path: str) -> Iterator[sqlite3.Connection]:
    """A connection per request (a FastAPI dependency via routes.get_db)."""
    with closing(connect(path)) as conn:
        yield conn
