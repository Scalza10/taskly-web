import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, routes
from .settings import Settings

# On Windows, mimetypes reads .js from the registry, which can say text/plain;
# browsers then refuse to run the page's module script.
mimetypes.add_type("text/javascript", ".js")


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory: uvicorn runs it with --factory, tests pass their own Settings."""
    settings = settings or Settings()
    db.migrate(settings.db_path)

    app = FastAPI(title="Taskly")
    app.state.settings = settings
    app.include_router(routes.router)
    # Last, so the API routes above win. html=True serves index.html at /.
    # No folder means no build yet (frontend/, npm run build): the API still works.
    static = Path(settings.static_dir)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app
