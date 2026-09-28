# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small shared to-do list: FastAPI + SQLite (stdlib `sqlite3`, no ORM) + a plain HTML/JS page, in one Docker container. It runs on the same VM as the Reels app (`C:\Project\ReelsTranslator`), behind that VM's shared Caddy. README.md covers running, the API, the database and deploying.

## Commands

The dev machine is Windows; use the venv's interpreter.

```powershell
.venv\Scripts\python.exe -m pytest                                   # all tests, under a second
.venv\Scripts\python.exe -m pytest tests/test_api.py::test_delete    # one test
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # http://localhost:8000, reads .env
docker compose up -d --build                                         # http://localhost:8001; needs `docker network create web` once
.\scripts\deploy.ps1                                                 # deploy the last commit on main
```

No linter or formatter is configured.

## Architecture

- **App factory.** `create_app(settings=None)` in `main.py` runs `db.migrate`, adds `routes.router`, and mounts `static/` at `/` last (so API routes win; `html=True` serves `index.html`). Tests pass their own `Settings`.
- **Database.** `db.py`: `connect()` sets `row_factory`, foreign keys and a busy timeout; `migrate()` sets WAL and applies `MIGRATIONS[user_version:]`, each as one `executescript` transaction that also bumps `PRAGMA user_version`. **Only append to `MIGRATIONS`; never edit or reorder a deployed one.** Each request gets its own connection (`routes.get_db` → `db.session`).
- **Queries** live in `todos.py` and return plain dicts (`done` as a bool). Routes stay thin: validate with pydantic (`Title` strips and bounds length), call `todos`, map `None`/`False` to 404.
- **Frontend** (`taskly/static/`). Plain HTML/CSS/ES module, no build step, no JS dependencies. After every change `app.js` reloads the list from the server rather than patching the DOM. Keep all assets local: no CDNs or other sites.
- **Settings** (`settings.py`) read the environment and `.env` in the working directory. Only `DB_PATH` so far.

## Deployment (shared VM)

The VM runs one Caddy (`~/proxy`, owns 80/443) and several apps, each its own Compose project in its own folder. Things that must stay true:

- **`~/taskly` is the only thing a deploy touches.** Never add steps to `deploy.ps1` that restart Caddy, touch `~/proxy`, or run compose outside `~/taskly`. The Caddyfile block for this site is added by hand (README, "First deploy").
- **The alias is `taskly`, the host port is 8001.** `docker-compose.yml` joins the external network `web` with alias `taskly`, which Caddy uses (`reverse_proxy taskly:8000`). Aliases must be unique across apps on `web`. Reels already binds `127.0.0.1:8000` on the VM, so this app's host port is `127.0.0.1:8001`. Never publish a port on `0.0.0.0`.
- **`name: taskly` in `docker-compose.yml`** pins the Compose project name, so it doesn't depend on the folder a clone lives in.
- **Data lives only in `./data` (mounted at `/data`).** Anything written elsewhere in the container is lost on the next deploy.
- **The VM's IP and host name are never committed.** `deploy.ps1` reads them from `scripts/deploy.local.psd1` (gitignored; template `deploy.local.example.psd1`), handed over with the SSH key on a USB stick. Docs use `<site>` and `<vm-ip>`.
- **`deploy.ps1` ships the last commit via `git archive`**, not the working tree. It sets TLS 1.2 explicitly because Windows PowerShell 5.1 doesn't offer it by default.
- **The site is behind Caddy's `basic_auth`** (the app has no login), except `/health`, which the deploy script checks. If the app gets its own login, remove that from the Caddyfile block. README "Caddy: the address and the password" is the how-to for passwords, logins, the address and Caddy errors; keep it current when giving Caddy instructions.
- **`/health` touches the database**, so a broken volume fails the deploy check instead of the first request.

## Things we learned

### Caddy on the shared VM (found on the first deploy)
- **`caddy` exists only inside the container.** Every Caddy command is `docker compose exec -w /etc/caddy caddy caddy <command>`, run in `~/proxy`. Without `-w /etc/caddy`, `reload` looks in the container's working directory `/srv` and fails with "no config file to load"; that is how the first reload silently never happened, and the browser showed `ERR_CONNECTION_CLOSED` (Caddy had no block for the name).
- **Always `validate` before `reload`.** Caddy is shared with Reels. A failed reload is safe (Caddy keeps its running config), but a bad config that validates would hit both sites.
- **`basic_auth` takes a bcrypt hash (`$2a$14$…`, ~60 chars), never the password.** A plain password or a truncated hash fails the reload with `base64-decoding password: illegal base64 data at input byte 1`. Make it with `caddy hash-password --plaintext '<pw>'` (single quotes).
- **Never route a hash through `sed` or `echo "..."`**: in double quotes the shell expands `$2`, `$14`… and silently mangles it. Tell people to paste with `nano`.
- **The Caddyfile is a read-only single-file bind mount.** `caddy fmt --overwrite` can't run in the service container; use `docker run --rm -v ~/proxy/Caddyfile:/etc/caddy/Caddyfile caddy:2 caddy fmt --overwrite /etc/caddy/Caddyfile`. An editor that replaces the file (new inode) leaves the container on the old copy until `docker compose up -d --force-recreate caddy`. `nano` writes in place. The "Caddyfile input is not formatted" warning is harmless.
- **The real site name stays out of the repo** like the VM's IP: docs say `<site>`; it lives in `deploy.local.psd1` and `~/proxy/Caddyfile`.

### App
- **On Windows, `mimetypes` can map `.js` to `text/plain`** from the registry, and browsers then refuse the module script. `main.py` forces `text/javascript`; `test_page_and_its_files_are_served` guards it.
- **`Settings` reads `.env` from the working directory.** Tests build settings with `tests/conftest.py::make_settings(tmp_path)`, which passes `_env_file=None`. Use it.
- **`[hidden] { display: none !important; }`** in `style.css` keeps `el.hidden` working against author `display` rules.

## Process

Small commits prefixed `feat:`, `fix:` or `docs:`. Default branch `main`.
