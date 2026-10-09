"""Taskly as an OAuth 2.1 authorization server, so an agent (Claude, Gemini) can connect to /mcp as you.

The discovery documents (RFC 9728, RFC 8414), dynamic client registration (RFC 7591), the sign-in
and consent page, and the token endpoint, with PKCE (S256) and a resource (RFC 8707) on every code.
The site's address comes from the request, like auth._same_origin: https://<site> behind Caddy,
http://localhost:8000 locally. Unlike /api, these answer with Response objects; none sets a cookie."""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import auth, oauth, oauth_page, passwords, sessions, users
from .deps import Conn

MCP_PATH = "/mcp"
CHALLENGE = re.compile(r"[A-Za-z0-9._~-]{43,128}")
# What the page posts back: everything the agent sent, carried in hidden fields.
FIELDS = ("response_type", "client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method",
          "scope", "resource")

router = APIRouter()


def site(request: Request) -> str:
    return f"{request.url.scheme}://{request.headers.get('host')}"


def mcp_url(request: Request) -> str:
    """The MCP endpoint's address: the resource every token is for."""
    return site(request) + MCP_PATH


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource(request: Request) -> dict:
    return {
        "resource": mcp_url(request),
        "authorization_servers": [site(request)],
        "scopes_supported": [oauth.SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Taskly",
    }


@router.get("/.well-known/oauth-authorization-server")
def authorization_server(request: Request) -> dict:
    # No client_id_metadata_document_supported: that would have us fetch URLs that clients name.
    # Claude, Claude Code and Gemini fall back to registering (/oauth/register).
    base = site(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [oauth.SCOPE],
        "authorization_response_iss_parameter_supported": True,
    }


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status)


@router.post("/oauth/register")
async def register(request: Request, conn: Conn) -> Response:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _oauth_error("invalid_client_metadata", "Send the client's metadata as a JSON object")
    uris, name = body.get("redirect_uris"), body.get("client_name", "")
    if not isinstance(name, str) or len(name) > 100:
        return _oauth_error("invalid_client_metadata", "client_name must be text of at most 100 characters")
    if (not isinstance(uris, list) or not 1 <= len(uris) <= 5
            or not all(isinstance(uri, str) and len(uri) <= 500 for uri in uris)):
        return _oauth_error("invalid_redirect_uri", "Give 1 to 5 redirect_uris")
    refused = [uri for uri in uris if not oauth.redirect_allowed(uri)]
    if refused:
        return _oauth_error("invalid_redirect_uri", f"This server doesn't send codes to {refused[0]}")
    client = oauth.register_client(conn, name, uris)
    # A public client whatever it asked for: no secret, PKCE instead (RFC 7591 lets the server decide).
    return JSONResponse({
        "client_id": client["id"],
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, status_code=201)


@dataclass
class Authorization:
    client: dict
    redirect_uri: str
    state: str | None
    code_challenge: str
    resource: str


def _redirect(uri: str, params: dict) -> RedirectResponse:
    """303 to uri with params added to its query (303: the browser follows a POST with a GET)."""
    parts = urlsplit(uri)
    query = urlencode([*parse_qsl(parts.query), *((k, v) for k, v in params.items() if v is not None)])
    return RedirectResponse(urlunsplit(parts._replace(query=query)), status_code=303)


def _page(html: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status_code=status, headers=oauth_page.HEADERS)


def _check(request: Request, conn, params: dict) -> Authorization | Response:
    """The request as an Authorization, or the answer that refuses it. Until the client and its
    redirect are known good, errors show here; after that, they go back to the agent (RFC 6749 4.1.2.1)."""
    client = oauth.get_client(conn, params.get("client_id", ""))
    if client is None:
        return _page(oauth_page.problem("This app isn't registered with Taskly."), 400)
    redirect_uri = params.get("redirect_uri", "")
    if not oauth.redirect_matches(client["redirect_uris"], redirect_uri):
        return _page(oauth_page.problem("This app asked to be sent somewhere it didn't register."), 400)
    state = params.get("state")

    def back(error: str, description: str) -> RedirectResponse:
        return _redirect(redirect_uri, {"error": error, "error_description": description, "state": state,
                                        "iss": site(request)})

    if params.get("response_type") != "code":
        return back("unsupported_response_type", "Only response_type=code is supported")
    if params.get("code_challenge_method") != "S256" or not CHALLENGE.fullmatch(params.get("code_challenge", "")):
        return back("invalid_request", "PKCE with code_challenge_method=S256 is required")
    resource = params.get("resource") or mcp_url(request)
    if resource != mcp_url(request):
        return back("invalid_target", f"This server only gives access to {mcp_url(request)}")
    return Authorization(client, redirect_uri, state, params["code_challenge"], resource)


def _browser_user(request: Request, conn) -> dict | None:
    """Who is logged in to the Taskly page in this browser, if anyone."""
    token = request.cookies.get(auth.COOKIE)
    found = sessions.session_user(conn, token) if token else None
    if found is None:
        return None
    user, touched = found
    if touched:
        request.state.renew_session = token
    return user


def _consent(request: Request, found: Authorization, params: dict, user: dict | None, error: str = "",
             status: int = 200) -> HTMLResponse:
    fields = {name: params[name] for name in FIELDS if params.get(name) is not None}
    other = "/oauth/authorize?" + urlencode({**fields, "account": "other"})
    return _page(oauth_page.consent(client_name=found.client["name"], redirect_uri=found.redirect_uri,
                                    fields=fields, username=user["username"] if user else None,
                                    other_account_url=other, error=error), status)


@router.get("/oauth/authorize")
def authorize_page(request: Request, conn: Conn) -> Response:
    params = dict(request.query_params)
    found = _check(request, conn, params)
    if not isinstance(found, Authorization):
        return found
    user = None if params.get("account") == "other" else _browser_user(request, conn)
    return _consent(request, found, params, user)


def _sign_in(request: Request, conn, username: str, password: str) -> dict | str:
    """The user, or why not. The same throttle and timing as POST /api/login; no browser session."""
    try:
        if not users.USERNAME.fullmatch(username):
            auth._attempt(request, None)
            passwords.verify_password(password, passwords.DUMMY_HASH)
            return "Wrong username or password"
        throttle, ip = auth._attempt(request, username)
    except HTTPException as refused:
        return refused.detail
    user = users.authenticate(conn, username, password)
    if user is None:
        return "Wrong username or password"
    throttle.succeeded(username, ip)
    return user


@router.post("/oauth/authorize")
async def authorize(request: Request, conn: Conn) -> Response:
    # auth's middleware has already refused a cross-site post (Origin), like a write to /api.
    form = await request.form()
    params = {name: value for name, value in form.items() if isinstance(value, str)}
    found = _check(request, conn, params)
    if not isinstance(found, Authorization):
        return found
    if params.get("action") != "allow":
        return _redirect(found.redirect_uri, {"error": "access_denied", "error_description": "You said no",
                                              "state": found.state, "iss": site(request)})
    if "username" in params:
        user = _sign_in(request, conn, params["username"].strip(), params.get("password", "")[:1024])
        if isinstance(user, str):
            return _consent(request, found, params, None, error=user, status=401)
    else:
        user = _browser_user(request, conn)
        if user is None:
            return _consent(request, found, params, None, error="Your session ended. Sign in again.", status=401)
    code = oauth.create_code(conn, client_id=found.client["id"], user_id=user["id"], redirect_uri=found.redirect_uri,
                             code_challenge=found.code_challenge, resource=found.resource)
    return _redirect(found.redirect_uri, {"code": code, "state": found.state, "iss": site(request)})


def _client_id(request: Request, form: dict) -> str:
    """client_id from the form, or from HTTP Basic if a client sends it there."""
    if form.get("client_id"):
        return form["client_id"]
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "basic":
        try:
            return base64.b64decode(value).decode().partition(":")[0]
        except (binascii.Error, UnicodeDecodeError):
            return ""
    return ""


@router.post("/oauth/token")
async def token(request: Request, conn: Conn) -> Response:
    form = {name: value for name, value in (await request.form()).items() if isinstance(value, str)}
    client_id = _client_id(request, form)
    if oauth.get_client(conn, client_id) is None:
        return _oauth_error("invalid_client", "Unknown client_id", 401)
    grant_type = form.get("grant_type")
    if grant_type == "authorization_code":
        # Taken first: a code is gone after one try, right or wrong.
        code = oauth.take_code(conn, form.get("code", ""))
        if (code is None or code["client_id"] != client_id or code["redirect_uri"] != form.get("redirect_uri")
                or not oauth.pkce_ok(form.get("code_verifier", ""), code["code_challenge"])):
            return _oauth_error("invalid_grant", "The code is wrong, used or expired")
        if form.get("resource", code["resource"]) != code["resource"]:
            return _oauth_error("invalid_target", "The resource doesn't match the code's")
        tokens = oauth.create_grant(conn, code)
    elif grant_type == "refresh_token":
        tokens = oauth.refresh(conn, form.get("refresh_token", ""), client_id)
        if tokens is None:
            return _oauth_error("invalid_grant", "The refresh token is wrong, used or expired")
    else:
        return _oauth_error("unsupported_grant_type", "Use authorization_code or refresh_token")
    return JSONResponse({"token_type": "Bearer", **tokens}, headers={"Pragma": "no-cache"})
