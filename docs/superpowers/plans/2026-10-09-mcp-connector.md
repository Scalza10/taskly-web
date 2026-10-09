# MCP connector: implementation plan

Design: [2026-10-09-mcp-connector-design.md](../specs/2026-10-09-mcp-connector-design.md).

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
