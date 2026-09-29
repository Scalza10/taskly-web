# Taskly

A small shared to-do list: a FastAPI app with a SQLite database and a plain
HTML/JS page. It runs in Docker on the same VM as Reels, behind the same
Caddy, on its own host name.

## Run it locally

**With Python and Node** (Python 3.12, Node 22.12 or newer), from the repo folder.
Once, and when requirements change:

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements-dev.txt
npm --prefix frontend install
```

Then, in two terminals:

```powershell
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # the API, port 8000
npm --prefix frontend run dev                                                    # the page, port 5173
```

Open <http://localhost:5173/>. Saving a file in `frontend/src` updates the page
at once; `--reload` restarts the API when you save a Python file. Stop either
with Ctrl+C. macOS or Linux: `.venv/bin/pip` and `.venv/bin/python`.

To see the page exactly as deployed, build it (`npm --prefix frontend run build`,
into `taskly/static/`) and open uvicorn's own <http://localhost:8000/>. Without a
build, port 8000 has only the API.

The database is created at `./data/taskly.db` and survives restarts; delete the
file to start empty. No `.env` is needed; copy `.env.example` to `.env` only to
put the database somewhere else (`DB_PATH`).

**With Docker** (the same container as on the VM):

```bash
docker network create web      # once; the compose file expects it (it's how Caddy reaches the app on the VM)
docker compose up -d --build
```

Open <http://localhost:8001/>. The database is `./data/taskly.db` on your
machine, mounted into the container.

**Tests:** `.venv\Scripts\python.exe -m pytest` for the API (under a second;
each test gets its own database, so your local data is untouched) and
`npm --prefix frontend test` for the page's logic.

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
  main.py       create_app(): runs the migrations, adds the routes, serves the built page
  settings.py   Settings (DB_PATH, STATIC_DIR), read from the environment and .env
  db.py         the SQLite connection and the schema migrations
  todos.py      the queries
  routes.py     the HTTP endpoints
  backup.py     python -m taskly.backup: copy the database to data/backups/
  migrate.py    python -m taskly.migrate: apply pending migrations
  static/       the built page (not in git)
frontend/
  src/          the page: React + TypeScript (api.ts talks to the API)
  vite.config.ts
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

**Backups.** Every deploy copies the database to
`~/taskly/data/backups/taskly-<UTC time>.db` before migrating, and keeps the
newest 10. To make one by hand (safe while the app runs):

```bash
cd ~/taskly
docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.backup
```

**Restoring a backup** (for example to go back to code from before a migration
that removed something):

```bash
cd ~/taskly
docker compose stop app
cp data/taskly.db data/taskly-before-restore.db
cp data/backups/taskly-<time>.db data/taskly.db
rm -f data/taskly.db-wal data/taskly.db-shm     # stale journal files would corrupt the restored copy
docker compose start app
```

Then deploy the code that matches that backup.

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
stay behind) and unpacks it into `~/taskly`. Then, on the VM: it builds the new
image while the old app keeps serving, backs up the database, runs the pending
migrations with the new image, and only then replaces the app, deletes the image
it replaced, and waits up to a minute for `https://<site>/health`. If the build
or a migration fails, it stops there and the old app keeps running on the
unchanged database. `-Branch` deploys another branch; `-Config` points at
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
3. **Add the site to Caddy, with a password.** The app has no login of its
   own, so Caddy asks for one. Follow [Changing the password](#changing-the-password)
   to make a hash, then add this block to `~/proxy/Caddyfile` and apply it as in
   [Editing the Caddyfile](#editing-the-caddyfile):

   ```
   <site> {
       @protected not path /health
       basic_auth @protected {
           taskly <the hash>
       }
       reverse_proxy taskly:8000
   }
   ```

   `/health` stays open so the deploy script can check it. Caddy gets the
   certificate by itself within a minute.
4. Open `https://<site>/` and log in as `taskly` with the password.

### On the VM

Run these inside `~/taskly`. Compose tells apps apart by folder, so the same
command in `~/reels` acts on Reels instead.

| To | Run |
|---|---|
| See the logs | `docker compose logs -f app` |
| Restart | `docker compose restart app` |
| Check the app without Caddy | `curl localhost:8001/health` |
| See Caddy's logs | `cd ~/proxy && docker compose logs -f caddy` |
| Change a setting | Edit `~/taskly/.env`, then `docker compose up -d` (a restart doesn't re-read it) |

## Caddy: the address and the password

Caddy runs in `~/proxy` and is **shared with Reels**: one Caddyfile, one
container, every site. A mistake there can affect Reels too, so always
validate before reloading. A reload that fails changes nothing: Caddy keeps
running the config it had, and both sites stay up.

### Editing the Caddyfile

Every command runs in `~/proxy`. Caddy is not installed on the VM itself, only
inside the container, so each `caddy` command goes through Docker.

1. Edit with `nano Caddyfile`. Nano writes the file in place. Editors that
   write a new file instead leave the container seeing the old one; if an edit
   seems ignored, `docker compose exec caddy grep -n <site> /etc/caddy/Caddyfile`
   shows what Caddy sees, and `docker compose up -d --force-recreate caddy`
   picks up the new file (Reels drops for a second or two).
2. Check it, then apply it:

   ```bash
   docker compose exec -w /etc/caddy caddy caddy validate    # ends with "Valid configuration"
   docker compose exec -w /etc/caddy caddy caddy reload      # no downtime for either site
   docker compose logs --tail 30 caddy                       # certificates, errors
   ```

   The `-w /etc/caddy` matters: without it Caddy looks in the wrong folder and
   answers "no config file to load".
3. Optional: tidy the indentation. A reload warns "Caddyfile input is not
   formatted" when it's uneven, which is harmless. The container can only read
   the file, so format it with a throwaway container, then reload:

   ```bash
   docker run --rm -v ~/proxy/Caddyfile:/etc/caddy/Caddyfile caddy:2 caddy fmt --overwrite /etc/caddy/Caddyfile
   ```

### Changing the password

The Caddyfile holds a **hash** of the password, never the password itself.

1. Make the hash (keep the single quotes, so `!` or `$` in the password
   arrive as typed):

   ```bash
   docker compose exec caddy caddy hash-password --plaintext 'purple-lamp-river'
   ```

2. It prints one line starting with `$2a$14$`, about 60 characters. Paste the
   whole line **with nano** in place of the old hash, after the user name:

   ```
   basic_auth @protected {
       taskly $2a$14$...
   }
   ```

   Don't paste it through `sed` or `echo "..."`: in double quotes the shell
   reads `$2`, `$14` and so on as variables and silently cuts them out.
3. Validate and reload as above. Everyone has to log in again with the new one.

Easy to type is fine, but not a single word or `1234`: the site is public and
Caddy doesn't limit login attempts. Three random words work well on a phone.

### Adding or removing a login

Each line in the `basic_auth` block is one user name and its hash. To give
someone their own login (so it can be taken away without changing everyone's
password), add a line with a new name and a hash made as above:

```
basic_auth @protected {
    taskly $2a$14$...
    maria  $2a$14$...
}
```

To remove one, delete its line. Validate and reload either way.

### Changing the address

1. Create the new DuckDNS subdomain, pointing at the same IP, and check it
   with `nslookup <new site>`.
2. Replace the site name on the block's first line in the Caddyfile. Validate
   and reload. Caddy gets the new certificate by itself.
3. Change `Site` in every developer's `scripts\deploy.local.psd1`, or the
   deploy's health check waits on the old address.

### Removing the password

Only once the app has a login of its own: remove the `@protected` line and
the `basic_auth` block, leaving `reverse_proxy taskly:8000`. Validate and
reload.

### When something goes wrong

| What you see | Why | Fix |
|---|---|---|
| `Error: no config file to load` on reload | `-w /etc/caddy` is missing | Use the commands in [Editing the Caddyfile](#editing-the-caddyfile) |
| `base64-decoding password: illegal base64 data at input byte 1` | The value after the user name isn't a hash: a plain password, or a hash cut short or mangled by the shell | [Changing the password](#changing-the-password); paste with nano |
| `WARN Caddyfile input is not formatted` | Uneven indentation | Harmless. Format it (step 3 above) if you like |
| `caddy: command not found` | Caddy exists only inside the container | Prefix with `docker compose exec -w /etc/caddy caddy` |
| Browser: `ERR_CONNECTION_CLOSED` | Caddy has no block for that name: the reload didn't happen or failed, or the name is misspelled | Validate, reload, check the logs |
| An edit seems ignored | The editor replaced the file and the container still sees the old one | `docker compose up -d --force-recreate caddy` |
| Browser: 502 | Caddy is fine but can't reach the app | `curl localhost:8001/health` on the VM; `docker network inspect web` should list `taskly-app-1` |
| Certificate errors in the logs | DNS doesn't point at the VM yet | `nslookup <site>`; fix the IP in DuckDNS, Caddy retries by itself |
| The deploy's health check fails but `curl localhost:8001/health` works | Caddy's side: a missing or wrong block, or `Site` in `deploy.local.psd1` doesn't match it | Compare the two names |

