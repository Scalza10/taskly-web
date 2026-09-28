# Taskly

A small shared to-do list: a FastAPI app with a SQLite database and a plain
HTML/JS page. It runs in Docker on the same VM as Reels, behind the same
Caddy, on its own host name.

## Run it locally

**With Python** (3.12; on Windows use `.venv\Scripts\python.exe` for `python`):

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip.exe
python -m uvicorn taskly.main:create_app --factory --reload
```

Open <http://localhost:8000/>. The database is created at `./data/taskly.db`
(change it with `DB_PATH` in `.env`, from `.env.example`).

**With Docker** (the same container as on the VM):

```bash
docker network create web      # once; the compose file expects it (it's how Caddy reaches the app on the VM)
docker compose up -d --build
```

Open <http://localhost:8001/>. The database is `./data/taskly.db` on your
machine, mounted into the container.

**Tests:** `python -m pytest` (a few seconds; each test gets its own database).

## API

| Method and path | Body | Answer |
|---|---|---|
| `GET /health` | | `{"status": "ok"}`; also checks the database |
| `GET /api/todos` | | Every todo, open ones first, then newest first |
| `POST /api/todos` | `{"title": "Buy milk"}` | 201 and the new todo |
| `PATCH /api/todos/{id}` | `{"title": ...}` and/or `{"done": true}` | The todo, or 404 |
| `DELETE /api/todos/{id}` | | 204, or 404 |

A todo is `{"id", "title", "done", "created_at", "updated_at"}`, times in UTC
(`2026-09-28T12:00:00Z`). Titles are trimmed and must be 1–500 characters (422
otherwise). Interactive docs are at `/docs`.

## Layout

```
taskly/
  main.py       create_app(): runs the migrations, adds the routes, serves static/
  settings.py   Settings (DB_PATH), read from the environment and .env
  db.py         the SQLite connection and the schema migrations
  todos.py      the queries
  routes.py     the HTTP endpoints
  static/       index.html, app.js, style.css (no build step)
tests/
scripts/deploy.ps1
```

## The database

One SQLite file: `/data/taskly.db` in the container, which is
`~/taskly/data/taskly.db` on the VM. Deploys never touch it.

**Changing the schema:** append an SQL string to `MIGRATIONS` in `db.py`, for
example `"ALTER TABLE todos ADD COLUMN due_date TEXT;"`. On startup the app runs
every migration the file hasn't had yet (it tracks them in `PRAGMA
user_version`), each in its own transaction. Never edit or reorder a migration
that has been deployed: the VM's database already ran it and won't run it again.

**Backup** (on the VM; safe while the app runs):

```bash
cd ~/taskly
docker compose exec app python -c "import sqlite3; sqlite3.connect('/data/taskly.db').backup(sqlite3.connect('/data/backup.db'))"
cp data/backup.db ~/taskly-$(date +%F).db
```

## Deploy

### How the VM is laid out

The VM runs one Caddy and several apps, each a separate Docker Compose project
in its own folder:

- `~/proxy`: Caddy. It owns ports 80 and 443, gets HTTPS certificates, and
  sends each host name in `~/proxy/Caddyfile` to its app over the Docker
  network `web`.
- `~/reels`: the Reels app.
- `~/taskly`: this app. It joins `web` as `taskly`, listens on 8000 inside the
  container, and on the VM itself only on `127.0.0.1:8001`.

A deploy rebuilds and restarts only `~/taskly`. Caddy and Reels keep running.

### Setting up a developer's PC (once per person)

You need three things, handed over on a USB stick, never through git or chat:

1. **The SSH private key** (`reels_oci`). Put it in `C:\Users\<you>\.ssh\`.
   OpenSSH refuses a key that other users can read, so restrict it in PowerShell:

   ```powershell
   icacls $HOME\.ssh\reels_oci /inheritance:r /grant:r "$($env:USERNAME):R"
   ```

2. **Its passphrase.** The deploy asks for it twice. To type it once per
   Windows login, enable the agent in an **Administrator** PowerShell:

   ```powershell
   Get-Service ssh-agent | Set-Service -StartupType Automatic
   Start-Service ssh-agent
   ```

   Then, in a normal window: `ssh-add $HOME\.ssh\reels_oci`.

3. **`scripts\deploy.local.psd1`** with the VM's IP, the site's host name and
   the key's path. Copy `scripts\deploy.local.example.psd1` and fill it in. Git
   ignores it, so the VM's address never ends up in the repo.

Check it works: `ssh -i $HOME\.ssh\reels_oci ubuntu@<vm-ip> "docker ps"`.

### Deploying

```powershell
.\scripts\deploy.ps1
```

It ships the last **commit** on `main` (`git archive`, so uncommitted changes
stay behind), unpacks it into `~/taskly`, runs `docker compose up -d --build`,
deletes the image it replaced, and waits up to a minute for
`https://<site>/health`. `-Branch` deploys another branch; `-Config` points at
another settings file.

Whoever deploys last wins: the VM gets exactly that person's commit. **Pull
before you deploy**, so you don't roll back the other person's changes.

### First deploy (once, on the VM)

1. **DNS.** Create the DuckDNS subdomain and point it at the VM's IP, the same
   one as Reels. Check it with `nslookup <site>`. No new firewall ports: all
   sites share 80 and 443.
2. **Deploy** with `.\scripts\deploy.ps1`. The health check at the end fails
   this first time because Caddy doesn't know the site yet. Check the app itself
   on the VM with `curl localhost:8001/health`.
3. **A password.** The app has no login of its own, so Caddy asks for one.
   Make its hash on the VM:

   ```bash
   cd ~/proxy && docker compose exec caddy caddy hash-password --plaintext '<the password>'
   ```

4. **Add the site** to `~/proxy/Caddyfile`, with that hash:

   ```
   <site> {
       @protected not path /health
       basic_auth @protected {
           taskly <the hash>
       }
       reverse_proxy taskly:8000
   }
   ```

   `/health` stays open so the deploy script can check it. Apply it with
   `docker compose exec caddy caddy reload` (in `~/proxy`). Reels isn't
   interrupted, and Caddy gets the certificate by itself within a minute.
5. Open `https://<site>/` and log in as `taskly` with the password.

### On the VM

Run these inside `~/taskly`. Compose tells apps apart by folder, so the same
command in `~/reels` acts on Reels instead.

| To | Run |
|---|---|
| See the logs | `docker compose logs -f app` |
| Restart | `docker compose restart app` |
| Check the app without Caddy | `curl localhost:8001/health` |
| See Caddy's logs | `cd ~/proxy && docker compose logs -f caddy` |
