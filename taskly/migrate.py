"""`python -m taskly.migrate`: apply pending schema migrations and say what changed.

deploy.ps1 runs it with the new image before starting the new app, so a failing migration
stops the deploy while the old app keeps running. The app also migrates on startup."""

from . import db
from .settings import Settings


def run(path: str) -> str:
    before = db.current_version(path)
    after = db.migrate(path)
    return f"schema {before} -> {after}" if after != before else f"schema {after}, nothing to do"


def main() -> None:
    print(run(Settings().db_path))


if __name__ == "__main__":
    main()
