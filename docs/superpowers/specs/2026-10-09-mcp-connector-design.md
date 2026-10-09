# Taskly as an MCP connector for Claude (and Gemini, by the standard)

## Context

The user wants to talk to an AI agent (Claude, ideally also Gemini) about their Taskly lists, using the
deployed server at `https://<site>` and their existing Taskly account. First version: see open tasks,
see all tasks, create a list, add tasks (to any list, including a new one), close tasks.

Decisions already made with the user:
- **Plain MCP tools**, no MCP Apps UI widget (it can be layered on later without changing the tools).
- **OAuth sign-in**, since claude.ai web, desktop and mobile only connect custom servers through OAuth.
  Claude sends the user to a Taskly sign-in and consent page (the usual username and password, or
  nothing when already logged in in that browser). Claude Code does the same OAuth.
- **Claude first, Gemini by the standard.** The Gemini app's "Custom apps" is US-only, and its OAuth
  is reported to never reach `/token`. Gemini CLI dropped Pro/Ultra subscriptions on 2026-06-18. We
  build to the spec (including DCR, which Gemini uses), allow Gemini's callback hosts, verify with
  Claude, and record the Gemini result in the README.

Research facts this design relies on (sources are in the research notes, summarized):
- MCP spec 2026-07-28 is stateless (no `initialize`, no sessions), but Claude documents the
  2025-03-26/06-18/11-25 versions. The Python SDK `mcp` 2.x (`MCPServer`, `streamable_http_app()`)
  serves both eras. Pin `mcp==2.3.0`.
- MCP auth: Protected Resource Metadata (RFC 9728) and a 401 with `WWW-Authenticate: Bearer
  resource_metadata=…`, AS metadata (RFC 8414) with `issuer` equal to the fetch origin, PKCE S256,
  `resource` (RFC 8707) checked as the token's audience. Registration: CIMD is recommended, and DCR
  is deprecated but still supported by Claude, Claude Code and Gemini.
- claude.ai details: callback `https://claude.ai/api/mcp/auth_callback` (and `claude.com`). PRM
  `resource` must equal the URL the user typed. Claude uses the first `authorization_servers` entry.
  The token endpoint must accept form-urlencoded bodies, rotate refresh tokens, return `invalid_grant`
  for dead refresh tokens, and answer within 10 s. Claude Code uses loopback redirects with any port.
- The SDK's built-in OAuth server provider is discouraged ("predates the AS/RS separation"). Its
  default host check answers 421 to non-localhost hosts. A mounted sub-app's lifespan never runs, so
  the host app must enter `session_manager.run()`.

## Design

### Shape
- **`/mcp`** is the MCP endpoint (Streamable HTTP; stateless, JSON responses). It is the SDK's ASGI
  app wrapped in our own small ASGI layer that does the following:
  - refuses a foreign `Origin` (403);
  - reads `Authorization: Bearer`, or answers 401 with `WWW-Authenticate`;
  - checks the token's resource equals `{origin}/mcp`;
  - puts the user in a `contextvars.ContextVar`;
  - sets `Cache-Control: no-store`.

  We don't use the SDK's `AuthSettings`/`TokenVerifier`: its well-known routes would land under the
  mount, and our wrapper is small and testable. It must answer at exactly `/mcp` with no 307 to
  `/mcp/`, and be registered before the static `/` mount.
- **Taskly is its own OAuth 2.1 authorization server** (hand-rolled; small):
  - `GET /.well-known/oauth-protected-resource` and `…/oauth-protected-resource/mcp` (PRM):
    `resource={origin}/mcp`, `authorization_servers=[origin]`, `scopes_supported=["tasks"]`.
  - `GET /.well-known/oauth-authorization-server`: issuer `{origin}`; endpoints `/oauth/authorize`,
    `/oauth/token`, `/oauth/register`; `code` only; `authorization_code` and `refresh_token`; S256
    only; `token_endpoint_auth_methods_supported=["none"]`; `scopes_supported=["tasks"]`;
    `authorization_response_iss_parameter_supported=true`. CIMD is not advertised (it would mean
    fetching client URLs from our server, an SSRF surface), so Claude falls back to DCR.
  - `POST /oauth/register` (DCR, RFC 7591): public clients only. Answers
    `token_endpoint_auth_method: "none"` even if a secret method was asked for; see the risk below.
    Every redirect URI must match the **allowlist**:
    - the exact claude.ai and claude.com callbacks;
    - `http://localhost` and `http://127.0.0.1` with any port and path (Claude Code, RFC 8252);
    - `https://oauth-redirect*.googleusercontent.com/…` (Gemini);
    - `https://antigravity.google/oauth-callback`.

    Bounds: name ≤ 100, ≤ 5 URIs, each ≤ 500. Unused clients older than a day are pruned on each
    registration. The allowlist is what stops a registered "client" from phishing a code to an
    attacker's site.
  - `GET /oauth/authorize` checks client_id and redirect_uri. If either is bad, it shows an error
    page and never redirects. Otherwise, wrong `response_type`, missing or non-S256
    `code_challenge`, or a `resource` other than `{origin}/mcp` redirect back with `error=…&state`.
    It then renders a server-side HTML page (no React, no JS, inline CSS, light and dark):
    - with a valid `taskly_session` cookie: "Signed in as maria. Allow *Claude* (`claude.ai`) to see
      and change your Taskly lists and tasks?", Allow/Cancel, and a "use another account" link that
      shows the fields;
    - without one: username and password fields plus Allow.
  - `POST /oauth/authorize` re-validates everything:
    - The password path uses the existing throttle (`auth._attempt`, `users.authenticate`,
      `throttle.succeeded`). It doesn't create a browser session.
    - Allow makes a single-use code (5 min; bound to client, redirect_uri, challenge, resource, user)
      and answers 303 to `redirect_uri?code&state&iss`. Cancel redirects with `access_denied`.
  - `POST /oauth/token` (form-urlencoded) handles two grants:
    - `authorization_code` checks PKCE, redirect_uri, client and resource. The code is single-use
      (deleted on use).
    - `refresh_token` rotates: the old token is deleted, and an unknown or reused one gets
      `invalid_grant`.

    Answers `{access_token, token_type:"Bearer", expires_in:3600, refresh_token, scope:"tasks"}`.
    Errors are RFC 6749 JSON with status 400 (401 for `invalid_client`), always `no-store`.
  - Access tokens last 1 h. Refresh tokens last 90 days and the clock restarts on each refresh, like
    sessions. Tokens and codes are `secrets.token_urlsafe(32)`, stored only as SHA-256 like
    `sessions.py`. Verification joins `users.disabled_at IS NULL`.
- **Origin is derived from the request** (`{request.url.scheme}://{Host}`), the same way
  `auth._same_origin` does it. uvicorn's proxy headers make it `https://<site>` on the VM and
  `http://localhost:8000` locally. No new setting, and the site name stays out of the repo.
- **Hardening.**
  - The auth middleware's Origin check extends to `POST /oauth/authorize`. Token and register calls
    come from servers without an Origin.
  - The sign-in page sends `X-Frame-Options: DENY` and a CSP with `frame-ancestors 'none'`, but
    **no `form-action`** (Chrome applies it to the 303 back to claude.ai).
  - `/oauth/*` and `/.well-known/*` answer `no-store`.
- **Service worker:** add `/^\/oauth\//`, `/^\/mcp/` and `/^\/\.well-known\//` to
  `navigateFallbackDenylist` in `frontend/vite.config.ts`. Otherwise an installed PWA would serve
  `index.html` for the sign-in page. Add the same three paths to the dev proxy.

### Tools (act as the signed-in user, with the same rights as the page)
| Tool | Args | Does | Hints |
|---|---|---|---|
| `list_lists` | – | your lists: id, name, owner, role, members, open/done counts | readOnly |
| `list_tasks` | `list?` (name or id), `include_done=false` | open tasks (or all) per list; every list when `list` is omitted | readOnly |
| `create_list` | `name` (ListName) | new list owned by you, returns it | – |
| `add_tasks` | `list` (name or id), `titles: list[Title]` (1–50) | adds tasks with server-made UUIDs, returns them | – |
| `complete_task` | `task_id`, `done=true` | closes a task; `done=false` reopens it (undo) | idempotent |

- A list reference is resolved by a helper: a UUID the user has a role in, otherwise a
  case-insensitive name among the user's lists. No match → error naming the user's lists. Several
  matches → error with their ids.
- Errors are tool errors (`isError` results with a plain message), never HTTP 5xx. Lists the user
  isn't in read as "not found", like the API's 404.
- The server's `instructions` say: use `list_lists` first, task ids come from `list_tasks`, and
  "close" means `complete_task`.
- Reuses `lists.role`, `lists.create_list`, `tasks.list_tasks`, `tasks.create_task`,
  `tasks.update_task`, `snapshot.list_view`, and `Title`/`ListName` from `routes.py`. The phone picks
  up changes on its next `/api/sync`, with no page changes.
- Each tool opens its own connection with `db.session(settings.db_path)`.

### Data: migration 4 (appended to `MIGRATIONS`)
- `oauth_clients(id TEXT PK, name, redirect_uris TEXT /*JSON*/, created_at)`
- `oauth_grants(id INTEGER PK, client_id → oauth_clients ON DELETE CASCADE, user_id → users ON DELETE CASCADE, resource, scope, created_at, last_used_at)`
- `oauth_codes(code_hash PK, client_id, user_id, redirect_uri, code_challenge, resource, scope, expires_at)`
- `oauth_tokens(token_hash PK, grant_id → oauth_grants ON DELETE CASCADE, kind CHECK IN ('access','refresh'), expires_at)`

Plus indexes on `oauth_grants.user_id` and `oauth_tokens.grant_id`. Expired codes and tokens are
deleted opportunistically on writes, like `create_session`. Each authorization makes a grant (one
"connection").

### Accounts
- `admin reset-password`, `disable-user` and `revoke-sessions` also delete the user's grants. They
  call a new `oauth.delete_user_grants` next to `sessions.delete_user_sessions`.
- `POST /api/me/password` also ends grants, because changing your password is how you sign out a
  lost device.
- `list-users` shows a connections count.

### New and changed files
- `taskly/oauth.py`: queries (clients, codes, grants, tokens, `token_user`, `delete_user_grants`) and
  the redirect allowlist.
- `taskly/oauth_routes.py`: well-known, register, authorize (GET/POST), token.
- `taskly/oauth_page.py`: the sign-in/consent HTML, escaped with `html.escape`.
- `taskly/mcp_server.py`: `MCPServer`, the tools, list resolution, the bearer ASGI wrapper, and
  `mcp_app()`.
- `taskly/main.py`: lifespan entering the session manager; include the OAuth router; add `/mcp`
  before the static mount.
- `taskly/auth.py`: the Origin check also covers `POST /oauth/authorize`, and `no-store` also covers
  `/oauth/` and `/.well-known/`.
- `taskly/db.py`: migration 4. `taskly/admin.py`: revocation as above.
- `requirements.txt`: `mcp==2.3.0`.
- `frontend/vite.config.ts`: denylist and dev proxy.
- Tests: `tests/test_oauth.py`, `tests/test_mcp.py`, plus revocation cases in the existing auth and
  admin tests.
- Docs:
  - **README**: a new "Connecting Claude (MCP)" section (below). The API section gets `/mcp`,
    `/oauth/*` and `/.well-known/*`. The database section gets migration 4. Accounts gets revoking
    connections.
  - **CLAUDE.md**: architecture bullets for MCP and OAuth (the wrapper rather than SDK auth, origin
    from request, the allowlist, no `form-action`, the SW denylist, the lifespan). Deployment notes
    that Caddy needs no change and that the tool contract must stay compatible, like the queue.
  - **`docs/data-model.html`** `MODEL` and **`docs/data-model.svg`**.

### Risks to check during implementation
- **SDK API names** (2.3.0: `MCPServer`, `streamable_http_app(stateless_http=…, json_response=…)`,
  the transport-security option, sync vs async tools, `ToolAnnotations`, raising a tool error).
  Check them with context7 / the SDK docs before writing code.
- **Starlette's `/mcp` → `/mcp/` redirect.** A test pins that `POST /mcp` is not a 3xx.
- **Claude's DCR may ask for `client_secret_post`.** If the live connect fails on that, issue a
  hashed secret and check it at `/token`.
- **Claude may send an `Origin` header to `/mcp`.** If the live connect is refused, allow that
  origin explicitly.

## Implementation tasks (branch `mcp`; merging and deploying wait for the user)

0. Copy this design to `docs/superpowers/specs/2026-10-09-mcp-connector-design.md` and the task list
   to `docs/superpowers/plans/2026-10-09-mcp-connector.md` (repo convention). Commit as `docs:`.
1. Migration 4 and `oauth.py` queries, with tests (TDD).
2. Well-known metadata, DCR and allowlist, with tests.
3. Authorize page GET/POST (cookie path, password path with throttle, cancel, bad client/redirect,
   framing headers, Origin refusal), with tests.
4. Token endpoint (PKCE, single-use code, resource, refresh rotation and reuse, disabled user), with
   tests.
5. `mcp_server.py`: wrapper (401 + `WWW-Authenticate`, wrong resource, no-store, exact `/mcp`), then
   tools. Tests use raw JSON-RPC over `TestClient` (`initialize`, `tools/list`, each tool, member vs
   outsider, ambiguous names, `add_tasks` showing in `/api/sync`).
6. Revocation in `admin.py` and the password change, with tests.
7. Frontend denylist and dev proxy; `npm test` and build.
8. Docs: README, CLAUDE.md, data-model page and SVG. Each step is its own small `feat:`/`docs:`
   commit.

## README "Connecting Claude (MCP)" (outline)
- **claude.ai (web/desktop):**
  1. Customize → Connectors → Add custom connector.
  2. Name it *Taskly* and use URL `https://<site>/mcp`; leave the OAuth fields empty, or pick
     "Register automatically".
  3. Connect, sign in on the Taskly page, then Allow. The phone app uses the same connector.
- **Claude Code:** `claude mcp add --transport http taskly https://<site>/mcp`, then `/mcp` to sign in.
  Locally use `http://localhost:8000/mcp`.
- **Gemini:** the status as tested, and its limits (US-only Custom apps, OAuth bug, CLI).
- **Disconnecting:** remove the connector in Claude. Then either `taskly.admin revoke-sessions <user>`
  or a password change ends all of a user's connections.
- **What the agent can do:** the five tools.

## Verification
- `.venv\Scripts\python.exe -m pytest` (all old and new tests), `npm --prefix frontend test`,
  `npm --prefix frontend run build`.
- Local end to end:
  1. Run uvicorn on :8000 with a local account.
  2. `claude mcp add --transport http taskly-local http://localhost:8000/mcp`, then `/mcp` to log in
     through the browser consent page.
  3. Ask Claude Code to list open tasks, create "Test list", add 3 tasks, and close one.
  4. Check in the page on :5173 that they appear after sync.
- After the user deploys: add the connector in claude.ai, run the same conversation on web and on
  the phone, and try Gemini if available. Record the outcomes in the README and the "Things we
  learned" section of CLAUDE.md.
