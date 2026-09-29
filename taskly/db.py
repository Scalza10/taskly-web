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
    """A connection per request (a FastAPI dependency via deps.get_db)."""
    with closing(connect(path)) as conn:
        yield conn
