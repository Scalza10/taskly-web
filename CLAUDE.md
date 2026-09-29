# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small shared to-do app with named lists: FastAPI + SQLite (stdlib `sqlite3`, no ORM) + a React + TypeScript page (built by Vite), in one Docker container. It runs on the same VM as the Reels app (`C:\Project\ReelsTranslator`), behind that VM's shared Caddy. README.md covers running, the API, the database and deploying.

## Commands

The dev machine is Windows; use the venv's interpreter.

```powershell
.venv\Scripts\python.exe -m pytest                                   # API tests, under a second
.venv\Scripts\python.exe -m pytest tests/test_tasks.py::test_delete    # one test
npm --prefix frontend test                                           # page logic tests (Vitest)
npm --prefix frontend run build                                      # typecheck + build into taskly/static/
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # API on :8000, reads .env
npm --prefix frontend run dev                                        # page on :5173, proxies /api to :8000
.venv\Scripts\python.exe -m taskly.admin add-user me                  # a local account, needed to use the page
docker compose up -d --build                                         # http://localhost:8001; needs `docker network create web` once
.\scripts\deploy.ps1                                                 # deploy the last commit on main
```

Node ≥ 22.12. No linter or formatter is configured.

## Architecture

- **App factory.** `create_app(settings=None)` in `main.py` runs `db.migrate`, adds `routes.router`, and mounts `settings.static_dir` at `/` last (so API routes win; `html=True` serves `index.html`), only if that folder exists: without a build the API still runs. Tests pass their own `Settings`; `make_settings` points `static_dir` at an empty tmp folder. HTML answers get `Cache-Control: no-cache` (index.html names the build's hashed files).
- **Database.** `db.py`: `connect()` sets `row_factory`, foreign keys and a busy timeout; `migrate()` sets WAL and applies `MIGRATIONS[user_version:]`, each as one `executescript` transaction that also bumps `PRAGMA user_version`. **Only append to `MIGRATIONS`; never edit or reorder a deployed one.** Each request gets its own connection (`deps.get_db` → `db.session`).
- **Accounts.** `passwords.py` (scrypt, at most 4 at once for memory), `users.py` and `sessions.py` are plain queries; `auth.py` is the FastAPI side: the `taskly_session` cookie, `CurrentUser` (every `/api` route but login and logout uses it), the login throttle (in memory, one process; checks and reserves each attempt under a lock, so parallel guesses can't pass the limit) and a middleware that refuses cross-site writes (`Origin` ≠ `scheme://host`), sets `Cache-Control: no-store` on `/api` and renews the cookie. Accounts are made with `python -m taskly.admin`; there is no sign-up. `deps.py` holds `get_db`/`Conn`. Endpoints return `None` with `status_code=` in the decorator, never a `Response` object: FastAPI drops cookies set on the injected `response` otherwise.
- **Queries** live in `users.py`, `sessions.py`, `lists.py`, `tasks.py` and `snapshot.py` and return plain dicts (`done` as a bool, people as usernames). Routes stay thin: validate with pydantic (`Title`, `ListName` strip and bound length; ids are `UUID`), check the role with `require_role`/`task_for` (none → 404, member doing an owner's action → 403), call the queries.
- **Lists.** Every list has an owner, who is also a member row. `GET /api/sync` is the only read endpoint for lists and tasks. Task ids are UUIDs made by the page; `POST /api/tasks` with an existing id in the same list is a retry and answers 200 unchanged.
- **Frontend** (`frontend/`). React + TypeScript, built by Vite into `taskly/static/` (gitignored; the Docker image builds it in a Node stage). `src/api.ts` is the only place that calls `fetch`; it throws `ApiError` with the server's `detail`. After every change the page reloads `/api/sync` rather than patching state. Keep all assets local: no CDNs or other sites. The dev server's proxy must not use `changeOrigin`.
- **Settings** (`settings.py`) read the environment and `.env` in the working directory. So far `DB_PATH`, `STATIC_DIR` (the built page) and `API_DOCS` (FastAPI's `/docs`, `/redoc`, `/openapi.json`; off by default and on the VM, since the site is public).

## Deployment (shared VM)

The VM runs one Caddy (`~/proxy`, owns 80/443) and several apps, each its own Compose project in its own folder. Things that must stay true:

- **`~/taskly` is the only thing a deploy touches.** Never add steps to `deploy.ps1` that restart Caddy, touch `~/proxy`, or run compose outside `~/taskly`. The Caddyfile block for this site is added by hand (README, "First deploy").
- **The alias is `taskly`, the host port is 8001.** `docker-compose.yml` joins the external network `web` with alias `taskly`, which Caddy uses (`reverse_proxy taskly:8000`). Aliases must be unique across apps on `web`. Reels already binds `127.0.0.1:8000` on the VM, so this app's host port is `127.0.0.1:8001`. Never publish a port on `0.0.0.0`.
- **`name: taskly` in `docker-compose.yml`** pins the Compose project name, so it doesn't depend on the folder a clone lives in.
- **Data lives only in `./data` (mounted at `/data`).** Anything written elsewhere in the container is lost on the next deploy.
- **The VM's IP and host name are never committed.** `deploy.ps1` reads them from `scripts/deploy.local.psd1` (gitignored; template `deploy.local.example.psd1`), handed over with the SSH key on a USB stick. Docs use `<site>` and `<vm-ip>`.
- **`deploy.ps1` ships the last commit via `git archive`**, not the working tree. On the VM it first removes every top-level entry of the archive from `~/taskly` (never `data/` or `.env`), then unpacks: unpacking over the old copy left files deleted in git behind, and the phase 2 deploy's build failed on a stale `TodoItem.tsx`. Then it builds, backs up (`python -m taskly.backup`), migrates (`python -m taskly.migrate`), then runs `docker compose up`. Backup and migrate run as `docker run --rm --network none … taskly-app`, never `docker compose run`: a compose one-off container joins `web` with alias `taskly` and could receive Caddy's traffic. It sets TLS 1.2 explicitly because Windows PowerShell 5.1 doesn't offer it by default.
- **The app does its own logins** (phase 1b). The site's Caddyfile block is only `reverse_proxy taskly:8000`; never add `basic_auth` back. README "Caddy: the address" is the how-to for the address and Caddy errors; keep it current when giving Caddy instructions.
- **The per-IP login throttle trusts uvicorn's `--forwarded-allow-ips=*`**, i.e. the leftmost `X-Forwarded-For`. That is safe only because Caddy replaces `X-Forwarded-For` from untrusted clients (its default). Never give the shared Caddy `trusted_proxies` or put a CDN in front without revisiting this.
- **`/health` touches the database**, so a broken volume fails the deploy check instead of the first request.

## Things we learned

### Caddy on the shared VM (found on the first deploy)
- **`caddy` exists only inside the container.** Every Caddy command is `docker compose exec -w /etc/caddy caddy caddy <command>`, run in `~/proxy`. Without `-w /etc/caddy`, `reload` looks in the container's working directory `/srv` and fails with "no config file to load"; that is how the first reload silently never happened, and the browser showed `ERR_CONNECTION_CLOSED` (Caddy had no block for the name).
- **Always `validate` before `reload`.** Caddy is shared with Reels. A failed reload is safe (Caddy keeps its running config), but a bad config that validates would hit both sites.
- **The Caddyfile is a read-only single-file bind mount.** `caddy fmt --overwrite` can't run in the service container; use `docker run --rm -v ~/proxy/Caddyfile:/etc/caddy/Caddyfile caddy:2 caddy fmt --overwrite /etc/caddy/Caddyfile`. An editor that replaces the file (new inode) leaves the container on the old copy until `docker compose up -d --force-recreate caddy`. `nano` writes in place. The "Caddyfile input is not formatted" warning is harmless.
- **The real site name stays out of the repo** like the VM's IP: docs say `<site>`; it lives in `deploy.local.psd1` and `~/proxy/Caddyfile`.

### App
- **On Windows, `mimetypes` can map `.js` to `text/plain`** from the registry, and browsers then refuse the module script. `main.py` forces `text/javascript`; `test_page_and_its_files_are_served` guards it.
- **`Settings` reads `.env` from the working directory.** Tests build settings with `tests/conftest.py::make_settings(tmp_path)`, which passes `_env_file=None`. Use it.
- **Tests log in.** The `client` fixture is logged in as `maria`; `anon` isn't. `fast_passwords` (autouse) lowers scrypt's cost; `test_passwords` checks the real one.

## Process

Small commits prefixed `feat:`, `fix:` or `docs:`. Default branch `main`.
