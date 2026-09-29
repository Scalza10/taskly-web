"""FastAPI dependencies shared by the routers."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from . import db


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from db.session(request.app.state.settings.db_path)


Conn = Annotated[sqlite3.Connection, Depends(get_db)]
