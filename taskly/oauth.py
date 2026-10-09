"""OAuth 2.1 for MCP connectors (Claude, Gemini): registered clients, one-time codes, and the
grants they turn into. A grant is one connection: one client, one user, its access and refresh tokens.

Codes and tokens are random, stored only as SHA-256, like sessions. Access tokens last ACCESS_LIFETIME;
a refresh token lasts REFRESH_LIFETIME and is replaced by a new one each time it is used."""

import base64
import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .sessions import TIME_FORMAT

SCOPE = "tasks"
CODE_LIFETIME = timedelta(minutes=5)
ACCESS_LIFETIME = timedelta(hours=1)
REFRESH_LIFETIME = timedelta(days=90)
UNUSED_CLIENT_LIFETIME = timedelta(days=1)

# Where a code may be sent. Anyone can register a client, so this list is what keeps a code
# from being phished to another site: only the agents we use, and the user's own machine.
EXACT_REDIRECTS = {
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "https://antigravity.google/oauth-callback",
}
GEMINI_REDIRECT_HOST = re.compile(r"oauth-redirect[a-z0-9-]*\.googleusercontent\.com")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format(when: datetime) -> str:
    return when.strftime(TIME_FORMAT)


def _split(uri: str):
    """urlsplit, or None for something that isn't a URL (a bad port raises)."""
    try:
        parts = urlsplit(uri)
        parts.port
        return parts
    except ValueError:
        return None


def _is_loopback(parts) -> bool:
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def redirect_allowed(uri: str) -> bool:
    """May a client register this redirect URI?"""
    if uri in EXACT_REDIRECTS:
        return True
    parts = _split(uri)
    if parts is None or parts.fragment or parts.username or parts.password:
        return False
    if _is_loopback(parts):
        return True  # a CLI on the user's own machine (Claude Code); any port and path (RFC 8252)
    return parts.scheme == "https" and bool(GEMINI_REDIRECT_HOST.fullmatch(parts.hostname or "")) and not parts.port


def redirect_matches(registered: list[str], uri: str) -> bool:
    """Is uri one of the client's redirect URIs? Exact, except a loopback's port may differ (RFC 8252)."""
    if uri in registered:
        return True
    parts = _split(uri)
    if parts is None or not _is_loopback(parts):
        return False
    for known in registered:
        other = _split(known)
        if other is not None and _is_loopback(other) and (other.hostname, other.path, other.query) == (
            parts.hostname, parts.path, parts.query
        ):
            return True
    return False


def pkce_ok(verifier: str, challenge: str) -> bool:
    """S256: the challenge is base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii", "replace")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(expected, challenge)


def register_client(conn: sqlite3.Connection, name: str, redirect_uris: list[str]) -> dict:
    """Dynamic client registration. The caller checks redirect_allowed first."""
    client_id = secrets.token_urlsafe(16)
    with conn:
        # Registration is open, so clients that never got a grant don't pile up.
        conn.execute(
            """DELETE FROM oauth_clients WHERE created_at < ?
               AND NOT EXISTS (SELECT 1 FROM oauth_grants g WHERE g.client_id = oauth_clients.id)""",
            (_format(_now() - UNUSED_CLIENT_LIFETIME),),
        )
        conn.execute(
            "INSERT INTO oauth_clients (id, name, redirect_uris) VALUES (?, ?, ?)",
            (client_id, name, json.dumps(redirect_uris)),
        )
    return {"id": client_id, "name": name, "redirect_uris": redirect_uris}


def get_client(conn: sqlite3.Connection, client_id: str) -> dict | None:
    row = conn.execute("SELECT id, name, redirect_uris FROM oauth_clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "redirect_uris": json.loads(row["redirect_uris"])}


def create_code(conn: sqlite3.Connection, *, client_id: str, user_id: int, redirect_uri: str,
                code_challenge: str, resource: str, scope: str = SCOPE) -> str:
    code = secrets.token_urlsafe(32)
    with conn:
        conn.execute("DELETE FROM oauth_codes WHERE expires_at < ?", (_format(_now()),))
        conn.execute(
            """INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, code_challenge, resource, scope,
                                        expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_hash(code), client_id, user_id, redirect_uri, code_challenge, resource, scope,
             _format(_now() + CODE_LIFETIME)),
        )
    return code


def take_code(conn: sqlite3.Connection, code: str) -> dict | None:
    """The code's row, deleted so it can't be used twice. None if unknown or expired."""
    with conn:
        row = conn.execute("DELETE FROM oauth_codes WHERE code_hash = ? RETURNING *", (_hash(code),)).fetchone()
    if row is None or row["expires_at"] < _format(_now()):
        return None
    return dict(row)


def _issue(conn: sqlite3.Connection, grant_id: int) -> dict:
    """A new access and refresh token for a grant. Runs inside the caller's transaction."""
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = _now()
    conn.execute("DELETE FROM oauth_tokens WHERE expires_at < ?", (_format(now),))
    conn.executemany(
        "INSERT INTO oauth_tokens (token_hash, grant_id, kind, expires_at) VALUES (?, ?, ?, ?)",
        [(_hash(access), grant_id, "access", _format(now + ACCESS_LIFETIME)),
         (_hash(refresh), grant_id, "refresh", _format(now + REFRESH_LIFETIME))],
    )
    return {"access_token": access, "refresh_token": refresh, "expires_in": int(ACCESS_LIFETIME.total_seconds())}


def create_grant(conn: sqlite3.Connection, code: dict) -> dict:
    """Turn a taken code into a grant and its first tokens."""
    with conn:
        conn.execute("DELETE FROM oauth_grants WHERE last_used_at < ?", (_format(_now() - REFRESH_LIFETIME),))
        grant_id = conn.execute(
            "INSERT INTO oauth_grants (client_id, user_id, resource, scope) VALUES (?, ?, ?, ?)",
            (code["client_id"], code["user_id"], code["resource"], code["scope"]),
        ).lastrowid
        return {**_issue(conn, grant_id), "scope": code["scope"]}


def refresh(conn: sqlite3.Connection, refresh_token: str, client_id: str) -> dict | None:
    """New tokens for a refresh token, which stops working. None if it is unknown, expired, another
    client's, or its user is disabled."""
    with conn:
        row = conn.execute(
            """SELECT t.token_hash, t.expires_at, g.id AS grant_id, g.client_id, g.scope
               FROM oauth_tokens t JOIN oauth_grants g ON g.id = t.grant_id JOIN users u ON u.id = g.user_id
               WHERE t.token_hash = ? AND t.kind = 'refresh' AND u.disabled_at IS NULL""",
            (_hash(refresh_token),),
        ).fetchone()
        if row is None or row["client_id"] != client_id or row["expires_at"] < _format(_now()):
            return None
        conn.execute("DELETE FROM oauth_tokens WHERE token_hash = ?", (row["token_hash"],))
        conn.execute("UPDATE oauth_grants SET last_used_at = ? WHERE id = ?", (_format(_now()), row["grant_id"]))
        return {**_issue(conn, row["grant_id"]), "scope": row["scope"]}


def token_user(conn: sqlite3.Connection, access_token: str, resource: str) -> dict | None:
    """The active user behind an access token meant for resource. None otherwise."""
    row = conn.execute(
        """SELECT u.id, u.username FROM oauth_tokens t
           JOIN oauth_grants g ON g.id = t.grant_id JOIN users u ON u.id = g.user_id
           WHERE t.token_hash = ? AND t.kind = 'access' AND t.expires_at >= ? AND g.resource = ?
             AND u.disabled_at IS NULL""",
        (_hash(access_token), _format(_now()), resource),
    ).fetchone()
    return None if row is None else {"id": row["id"], "username": row["username"]}


def delete_user_grants(conn: sqlite3.Connection, user_id: int) -> int:
    """Disconnect every agent a user connected. Returns how many connections ended."""
    with conn:
        conn.execute("DELETE FROM oauth_codes WHERE user_id = ?", (user_id,))
        return conn.execute("DELETE FROM oauth_grants WHERE user_id = ?", (user_id,)).rowcount
