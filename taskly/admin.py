"""Accounts from the command line. There is no sign-up page: the admin creates every account.

On the VM, in ~/taskly:  docker compose exec app python -m taskly.admin add-user maria
Locally:                 .venv\\Scripts\\python.exe -m taskly.admin add-user maria"""

import argparse
import getpass
import secrets
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing

from . import db, lists, sessions, users
from .settings import Settings


class AdminError(Exception):
    """Stops the command with a message and exit code 1."""


def _user(conn: sqlite3.Connection, name: str) -> dict:
    user = users.find_user(conn, name)
    if user is None:
        raise AdminError(f"No user {name}")
    return user


def _ask_password(prompt: Callable[[str], str], allow_generated: bool) -> tuple[str, bool]:
    """(password, generated). Empty answer makes one if allowed."""
    first = prompt("Password (empty: make one up): " if allow_generated else "Password: ")
    if not first and allow_generated:
        return secrets.token_urlsafe(12), True
    if prompt("Again: ") != first:
        raise AdminError("The passwords don't match")
    return first, False


def add_user(conn, args, prompt) -> None:
    users.check_username(args.name)
    password, generated = _ask_password(prompt, allow_generated=True)
    user = users.create_user(conn, args.name, password)
    print(f"Created {user['username']}.")
    claimed = lists.claim_unowned(conn, user["id"])
    if claimed:
        print(f"Now owns: {', '.join(claimed)}")
    if generated:
        print(f"Password: {password}")


def reset_password(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    password, generated = _ask_password(prompt, allow_generated=True)
    users.set_password(conn, user["id"], password)
    ended = sessions.delete_user_sessions(conn, user["id"])
    print(f"New password for {user['username']}; {ended} sessions ended.")
    if generated:
        print(f"Password: {password}")


def disable_user(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    for name, heir in lists.hand_over(conn, user["id"]):
        print(f"{name} now belongs to {heir}.")
    users.set_disabled(conn, user["id"], True)
    ended = sessions.delete_user_sessions(conn, user["id"])
    print(f"Disabled {user['username']}; {ended} sessions ended.")


def enable_user(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    users.set_disabled(conn, user["id"], False)
    print(f"Enabled {user['username']}.")


def revoke_sessions(conn, args, prompt) -> None:
    user = _user(conn, args.name)
    ended = sessions.delete_user_sessions(conn, user["id"])
    print(f"{user['username']}: {ended} sessions ended.")


def list_users(conn, args, prompt) -> None:
    for user in users.list_users(conn):
        state = "disabled" if user["disabled_at"] else "active"
        print(f"{user['username']:<32} {state:<8} {user['sessions']} sessions  (created {user['created_at']})")


COMMANDS = {
    "add-user": (add_user, "create an account"),
    "reset-password": (reset_password, "set a new password and log out everywhere"),
    "disable-user": (disable_user, "block logins and log out everywhere"),
    "enable-user": (enable_user, "allow logins again"),
    "revoke-sessions": (revoke_sessions, "log a user out everywhere"),
    "list-users": (list_users, "show every account"),
}


def main(argv: list[str] | None = None, *, settings: Settings | None = None,
         prompt: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog="python -m taskly.admin", description="Manage Taskly accounts.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        if name != "list-users":
            command.add_argument("name")
    args = parser.parse_args(argv)

    settings = settings or Settings()
    db.migrate(settings.db_path)
    with closing(db.connect(settings.db_path)) as conn:
        try:
            COMMANDS[args.command][0](conn, args, prompt)
        except (AdminError, users.UserError) as error:
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
