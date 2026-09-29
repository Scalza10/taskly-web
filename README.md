# Taskly

A small shared to-do app with named lists: a FastAPI app with a SQLite database and a React +
TypeScript page. It runs in Docker on the same VM as Reels, behind the same
Caddy, on its own host name.

## Run it locally

**With Python and Node** (Python 3.12, Node 22.12 or newer), from the repo folder.
Once, and when requirements change:

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements-dev.txt
npm --prefix frontend ci
```

Then, in two terminals:

```powershell
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # the API, port 8000
npm --prefix frontend run dev                                                    # the page, port 5173
```

Open <http://localhost:5173/>. The page asks you to log in, so create yourself
an account once (see [Accounts](#accounts)). Saving a file in `frontend/src` updates the page
at once; `--reload` restarts the API when you save a Python file. Stop either
with Ctrl+C. macOS or Linux: `.venv/bin/pip` and `.venv/bin/python`.

To see the page exactly as deployed, build it (`npm --prefix frontend run build`,
into `taskly/static/`) and open uvicorn's own <http://localhost:8000/>. Without a
build, port 8000 has only the API.

The service worker (offline and install) only runs on the build: use
`npm --prefix frontend run build` and uvicorn's <http://localhost:8000/> to try
them, with DevTools → Network → Offline. Opening the dev server from a phone on
your network (`http://<pc-ip>:5173`) doesn't work: adding tasks needs
`crypto.randomUUID()`, which browsers only offer on https or localhost.

The database is created at `./data/taskly.db` and survives restarts; delete the
file to start empty. No `.env` is needed; copy `.env.example` to `.env` only to
put the database somewhere else (`DB_PATH`).

**With Docker** (the same container as on the VM):

```bash
docker network create web      # once; the compose file expects it (it's how Caddy reaches the app on the VM)
docker compose up -d --build
```

Open <http://localhost:8001/>. The database is `./data/taskly.db` on your
machine, mounted into the container. Create an account first
(`docker compose exec app python -m taskly.admin add-user me`).

**Tests:** `.venv\Scripts\python.exe -m pytest` for the API (under a second;
each test gets its own database, so your local data is untouched) and
`npm --prefix frontend test` for the page's logic.

## API

| Method and path | Body | Answer |
|---|---|---|
| `GET /health` | | `{"status": "ok"}`; also checks the database |
| `POST /api/login` | `{"username", "password"}` | 204 and the session cookie; 401 if wrong; 429 after too many tries |
| `POST /api/logout` | | 204; ends this device's session and tells the browser to clear the site's saved data (`Clear-Site-Data: "storage"`) |
| `GET /api/me` | | `{"username"}` |
| `POST /api/me/password` | `{"current", "new"}` | 204; logs out your other devices. 403 if `current` is wrong, 422 if `new` is under 10 characters |
| `GET /api/sync` | | Everything you can see: `{"me", "lists": [{"id", "name", "owner", "role", "members", "tasks": [...]}]}`, lists by name, tasks open first then newest |
| `POST /api/lists` | `{"name": "Groceries"}` | 201 and the list; you own it |
| `PATCH /api/lists/{id}` | `{"name": ...}` | The list. Owner only |
| `DELETE /api/lists/{id}` | | 204; its tasks go too. Owner only |
| `POST /api/lists/{id}/members` | `{"username": "tom"}` | 201 (200 if already in). Owner only; 404 for a name that is unknown or disabled |
| `DELETE /api/lists/{id}/members/{username}` | | 204. The owner removes anyone; anyone can remove themselves (leave), except the owner (409) |
| `POST /api/tasks` | `{"id": "<uuid>", "list_id": "<uuid>", "title": "Milk"}` | 201 and the task. The same `id` again in the same list: 200 and the stored task (a safe retry). The same `id` in another list: 409 |
| `PATCH /api/tasks/{id}` | `{"title": ...}` and/or `{"done": true}` | The task |
| `DELETE /api/tasks/{id}` | | 204 |

Every `/api` endpoint except login needs the session cookie (401 otherwise).
Writes from another site (an `Origin` header that isn't this site) get 403.

A task is `{"id", "list_id", "title", "done", "created_by", "done_by",
"created_at", "updated_at"}`: people by username (`null` for tasks from before
accounts), times in UTC set by the server (`2026-09-28T12:00:00Z`). Task ids are
UUIDs the page makes itself. Titles are trimmed and 1–500 characters, list names
1–100 (422 otherwise). Anything in a list you're not in answers 404, as if it
didn't exist; an owner's action by a member answers 403. Interactive docs are at
`/docs` when `API_DOCS=true` is in `.env` (off by default, and on the VM: the
site is public).

## Accounts

There is no sign-up page: the admin creates every account. Hand passwords over
in person, not through chat.

On the VM, in `~/taskly` (`docker compose exec app python -m taskly.admin …`), or
locally (`.venv\Scripts\python.exe -m taskly.admin …`):

| To | Run |
|---|---|
| Create an account | `add-user maria`, then type the password twice, or press Enter to get a random one printed |
| Set a new password (also logs them out everywhere) | `reset-password maria` |
| Block someone (logs them out; their name stays on what they did) | `disable-user maria` |
| Let them back in | `enable-user maria` |
| Log someone out everywhere (a lost phone) | `revoke-sessions maria` |
| See everyone | `list-users` |

A list without an owner (the old list "Taskly", if it was migrated before any account existed) goes to the next account created. Disabling someone hands each list they own to the active member who joined it earliest; with no other active member, the list keeps its (disabled) owner.

For example, to create an account on the VM:

```bash
cd ~/taskly
docker compose exec app python -m taskly.admin add-user <name>
```

It asks for the password twice (at least 10 characters). Press Enter at the
first prompt instead to have one made up and printed. Do this once per person.
Names are 2–32 letters, digits, `.`, `_` or `-`; capitals don't matter when
logging in, and the page shows the name as it was created.

People can change their own password on the page; that also logs out their
other devices. Logins last 90 days from the last time the device was used.
After 10 wrong passwords for a name (or 30 from one address) in 15 minutes,
logins wait up to 15 minutes.

**Locally:** create yourself an account once with
`.venv\Scripts\python.exe -m taskly.admin add-user me`, then log in on the page.

## On your phone

Open `https://<site>/`, log in, then install it:

- **iPhone (Safari):** Share → **Add to Home Screen**. Do this: Safari deletes a
  website's saved data after 7 days without a visit, but not an installed app's,
  and unsent changes live there.
- **Android (Chrome):** menu → **Install app** (or "Add to Home screen").
- **Laptop (Chrome or Edge):** the install icon at the end of the address bar.

**Offline** you can see your lists and add, tick, rename and delete tasks. The
line at the bottom says how many changes are waiting; they're sent when you're
back online and the app is open (it doesn't sync in the background). Creating
lists, settings and logging out need a connection. If someone deleted a task you
changed offline, your change is dropped and the app says so.

**Logging out** removes everything Taskly saved on the device. If changes
haven't synced yet, it asks first. Someone else logging in on the same device
never sees or sends your unsent changes.

**Checking a new version on a phone:** after a deploy, close and reopen the app
(it updates on open). Then: go offline (airplane mode), tick a task, add one,
reopen the app (still there, "2 changes waiting"), go online, and check another
device shows the changes.

## Layout

```
taskly/
  main.py       create_app(): runs the migrations, adds the routes, serves the built page
  settings.py   Settings (DB_PATH, STATIC_DIR, API_DOCS), read from the environment and .env
  db.py         the SQLite connection and the schema migrations
  routes.py     the HTTP endpoints
  deps.py       the per-request database connection
  auth.py       the session cookie, the login check, the throttle, the cross-site guard
  passwords.py  password hashing (scrypt)
  users.py      the account queries
  sessions.py   the login session queries
  lists.py      lists and members: the queries
  tasks.py      tasks: the queries
  snapshot.py   what a user can see (GET /api/sync)
  admin.py      python -m taskly.admin: create and manage accounts
  backup.py     python -m taskly.backup: copy the database to data/backups/
  migrate.py    python -m taskly.migrate: apply pending migrations
  static/       the built page (not in git)
frontend/
  src/          the page: React + TypeScript (api.ts calls the API; sync.ts sends the queued task changes and downloads /api/sync)
    store.ts, view.ts, sync.ts, device.ts, useLocal.ts, StatusLine.tsx   the device's copy (IndexedDB) and its queue of unsent changes, what the screen shows, syncing, the page's one store and sync, the hook that triggers syncs, the "N changes waiting" line
    Login.tsx, AccountBar.tsx, ChangePassword.tsx   the login screen, the bar with your name, the password form
    ListsPage.tsx, ListPicker.tsx, NewList.tsx, ListSettings.tsx   the lists page: the picker, new list, members and rename/delete
    Tasks.tsx, TaskItem.tsx   the open list's tasks
    pickList.ts   which list is open
    messages.ts   the text shown for API errors
  public/       the icon (icon.svg) and the PNGs made from it (`npm --prefix frontend run icons`)
  vite.config.ts   Vite and the PWA plugin (manifest and service worker)
tests/
scripts/deploy.ps1
```

## The database

One SQLite file: `/data/taskly.db` in the container, which is
`~/taskly/data/taskly.db` on the VM. Deploys back it up and apply new migrations to it, but never replace it.

**Changing the schema:** append an SQL string to `MIGRATIONS` in `db.py`, for
example `"ALTER TABLE tasks ADD COLUMN due_date TEXT;"`. On startup the app runs
every migration the file hasn't had yet (it tracks them in `PRAGMA
user_version`), each in its own transaction. Never edit or reorder a migration
that has been deployed: the VM's database already ran it and won't run it again.

**Backups.** Every deploy copies the database to
`~/taskly/data/backups/taskly-<UTC time>.db` before migrating, and keeps the
newest 10. A backup taken right before a migration is named
`taskly-<UTC time>-before-schema-<N>.db` and the rotation never deletes it;
delete those by hand when you're sure you won't go back. Being root's, they need
a throwaway container, like the restore below:

```bash
docker run --rm --network none -v ~/taskly/data:/data taskly-app sh -c 'rm /data/backups/taskly-<time>-before-schema-3.db'
```

To make one by hand (safe while the app runs):

```bash
cd ~/taskly
docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.backup
```

**Restoring a backup.** The files in `data/` belong to root (the container's
user), so the copying happens in a throwaway container. With the app stopped:

```bash
cd ~/taskly
docker compose stop app
docker run --rm --network none -v ~/taskly/data:/data taskly-app sh -c '
  cp /data/taskly.db /data/taskly-before-restore.db &&
  cp /data/backups/taskly-<time>.db /data/taskly.db &&
  rm -f /data/taskly.db-wal /data/taskly.db-shm'    # stale journal files would corrupt the restored copy
```

Going back to before phase 2 means restoring the `taskly-<time>-before-schema-3.db` file; the ordinary
backups taken after it are already schema 3.

Then, depending on why:

- **Same code, the data went wrong:** `docker compose start app`.
- **Going back to older code** (for example from before a migration that removed
  something): don't start the app here; the running image would migrate the
  restored database forward again. From your PC, deploy the older code:
  `.\scripts\deploy.ps1 -Branch <commit>`. It backs up, finds nothing to migrate,
  and starts the older app.

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
stay behind) and replaces the code in `~/taskly` with it, so files deleted in git
go on the VM too; `data/` and `.env` stay. Then, on the VM: it builds the new
image while the old app keeps serving, backs up the database, runs the pending
migrations with the new image, and only then replaces the app, deletes the image
it replaced, and waits up to a minute for `https://<site>/health`. If the build
or a migration fails, it stops there and the old app keeps running on the
unchanged database. `-Branch` deploys another branch; `-Config` points at
another settings file. `-Branch` also takes a commit hash. Code from before these
deploy steps existed must be deployed with the `deploy.ps1` of that same commit (its
image has no `taskly.backup`).

Whoever deploys last wins: the VM gets exactly that person's commit. **Pull
before you deploy**, so you don't roll back the other person's changes.

### First deploy (once, on the VM)

1. **DNS.** Create the DuckDNS subdomain and point it at the VM's IP, the same
   one as Reels. Check it with `nslookup <site>`. No new firewall ports: all
   sites share 80 and 443.
2. **Deploy** with `.\scripts\deploy.ps1`. The health check at the end fails
   this first time because Caddy doesn't know the site yet. Check the app itself
   on the VM with `curl localhost:8001/health`.
3. **Add the site to Caddy.** Add this block to `~/proxy/Caddyfile` and apply it
   as in [Editing the Caddyfile](#editing-the-caddyfile):

   ```
   <site> {
       reverse_proxy taskly:8000
   }
   ```

   Caddy gets the certificate by itself within a minute.
4. **Create the accounts** as in [Accounts](#accounts) and open `https://<site>/`.

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

### Moving from Caddy's password to accounts (once, when phase 1b ships)

1. Deploy. Caddy still asks for its password, so for a few minutes people log in twice.
2. Create everyone's account (see [Accounts](#accounts)).
3. In `~/proxy/Caddyfile`, remove the `@protected` line and the `basic_auth { … }`
   block from the site's block, leaving `reverse_proxy taskly:8000`. Validate and
   reload as in [Editing the Caddyfile](#editing-the-caddyfile).
4. In a private browser window, `https://<site>/` shows Taskly's own login and no
   browser password prompt.

## Caddy: the address

Caddy runs in `~/proxy` and is **shared with Reels**: one Caddyfile, one
container, every site. For Taskly it only does HTTPS and forwarding; the logins
are the app's own (see [Accounts](#accounts)). A mistake there can affect Reels too, so always
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

### Changing the address

1. Create the new DuckDNS subdomain, pointing at the same IP, and check it
   with `nslookup <new site>`.
2. Replace the site name on the block's first line in the Caddyfile. Validate
   and reload. Caddy gets the new certificate by itself.
3. Change `Site` in every developer's `scripts\deploy.local.psd1`, or the
   deploy's health check waits on the old address.

### When something goes wrong

| What you see | Why | Fix |
|---|---|---|
| `Error: no config file to load` on reload | `-w /etc/caddy` is missing | Use the commands in [Editing the Caddyfile](#editing-the-caddyfile) |
| `WARN Caddyfile input is not formatted` | Uneven indentation | Harmless. Format it (step 3 above) if you like |
| `caddy: command not found` | Caddy exists only inside the container | Prefix with `docker compose exec -w /etc/caddy caddy` |
| Browser: `ERR_CONNECTION_CLOSED` | Caddy has no block for that name: the reload didn't happen or failed, or the name is misspelled | Validate, reload, check the logs |
| An edit seems ignored | The editor replaced the file and the container still sees the old one | `docker compose up -d --force-recreate caddy` |
| Browser: 502 | Caddy is fine but can't reach the app | `curl localhost:8001/health` on the VM; `docker network inspect web` should list `taskly-app-1` |
| Certificate errors in the logs | DNS doesn't point at the VM yet | `nslookup <site>`; fix the IP in DuckDNS, Caddy retries by itself |
| The deploy's health check fails but `curl localhost:8001/health` works | Caddy's side: a missing or wrong block, or `Site` in `deploy.local.psd1` doesn't match it | Compare the two names |

