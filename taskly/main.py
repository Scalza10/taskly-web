import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import auth, db, routes
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
    auth.install(app)
    app.include_router(routes.router)
    @app.middleware("http")
    async def revalidate_the_page(request, call_next):
        # index.html names this build's hashed asset files, so after a deploy browsers must
        # ask for it again; the hashed files themselves never change and can be cached.
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    # Last, so the API routes above win. html=True serves index.html at /.
    # No folder means no build yet (frontend/, npm run build): the API still works.
    static = Path(settings.static_dir)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app
