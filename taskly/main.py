import json
import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from . import auth, db, mcp_server, oauth_routes, routes
from .settings import Settings

# On Windows, mimetypes reads .js from the registry, which can say text/plain;
# browsers then refuse to run the page's module script.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")


async def invalid_request(request: Request, exc: RequestValidationError) -> Response:
    # FastAPI's own 422 echoes the input as UTF-8, which fails (a 500) on a lone surrogate:
    # valid JSON, and pydantic refuses it in any field with a length limit. Escape it instead.
    body = json.dumps({"detail": jsonable_encoder(exc.errors())}, ensure_ascii=True)
    return Response(body, status_code=422, media_type="application/json")


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory: uvicorn runs it with --factory, tests pass their own Settings."""
    settings = settings or Settings()
    db.migrate(settings.db_path)

    docs = settings.api_docs
    agents = mcp_server.build(settings)
    # The MCP SDK's session manager needs a task group for the app's lifetime.
    app = FastAPI(title="Taskly", docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
                  openapi_url="/openapi.json" if docs else None, lifespan=lambda app: mcp_server.running(agents))
    app.state.settings = settings
    app.add_exception_handler(RequestValidationError, invalid_request)
    auth.install(app)
    app.include_router(routes.router)
    app.include_router(oauth_routes.router)
    # A route, not a mount: exactly /mcp, the address agents are given (a mount would redirect to /mcp/).
    app.add_route(oauth_routes.MCP_PATH, mcp_server.Guard(agents, settings))
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
